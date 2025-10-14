from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, or_
from ..models.ticket import Ticket
from ..models.hardware import Hardware
from .inventory import ensure_ticket_usage_event, delete_ticket_event
from decimal import Decimal, InvalidOperation

from ..services.timecalc import compute_minutes, round_minutes
from ..services.clientsync import resolve_client_name, load_client_table
from ..core.config import settings
from ..core.barcodes import barcode_aliases, normalize_barcode

SIXTY = Decimal("60")


def list_tickets(db: Session, limit: int = 100, offset: int = 0):
    rows = db.execute(
        select(Ticket).order_by(desc(Ticket.created_at)).limit(limit).offset(offset)
    ).scalars().all()
    changed = False
    client_table = load_client_table()
    for ticket in rows:
        if _ensure_calculated_fields(ticket, initialize_invoice=True, client_table=client_table):
            changed = True
    if changed:
        db.commit()
    return rows


def list_active_tickets(db: Session, client_key: str | None = None, limit: int = 100, offset: int = 0):
    stmt = select(Ticket).where(
        Ticket.end_iso.is_(None),
        or_(Ticket.entry_type.is_(None), Ticket.entry_type != "hardware"),
    )
    if client_key:
        stmt = stmt.where(Ticket.client_key == client_key)
    stmt = stmt.order_by(desc(Ticket.created_at)).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    changed = False
    client_table = load_client_table()
    for ticket in rows:
        if _ensure_calculated_fields(ticket, initialize_invoice=True, client_table=client_table):
            changed = True
    if changed:
        db.commit()
    return rows

def get_ticket(db: Session, entry_id: int) -> Ticket | None:
    return db.get(Ticket, entry_id)


def _money_to_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace("$", "").replace(",", "")
        try:
            return float(Decimal(cleaned))
        except InvalidOperation:
            return None
    return None


def _to_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        cleaned = cleaned.replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return None
    return None


def _format_decimal(value: Decimal | None) -> str | None:
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.01"))
    return format(quantized, "f")


def _normalize_currency_input(value: object) -> str | None:
    if value is None:
        return None
    decimal_value = _to_decimal(value)
    if decimal_value is not None:
        return _format_decimal(decimal_value)
    if isinstance(value, str):
        trimmed = value.strip()
        return trimmed or None
    return None


def _support_rate_for_client(client_key: str | None, table: dict | None = None) -> Decimal | None:
    if not client_key:
        return None
    if table is None:
        table = load_client_table()
    entry = table.get(client_key) if isinstance(table, dict) else None
    if not isinstance(entry, dict):
        return None
    return _to_decimal(entry.get("support_rate"))


def _calculate_ticket_amount(ticket: Ticket, table: dict | None = None) -> Decimal | None:
    entry_type = (ticket.entry_type or "time").lower()
    if entry_type == "hardware":
        unit_price = _to_decimal(ticket.hardware_sales_price)
        if unit_price is None:
            return None
        quantity = ticket.hardware_quantity or 1
        try:
            quantity_decimal = Decimal(int(quantity))
        except (TypeError, ValueError, InvalidOperation):
            quantity_decimal = Decimal(1)
        return unit_price * quantity_decimal

    hours_decimal = _to_decimal(ticket.rounded_hours)
    if hours_decimal is None:
        minutes_value = ticket.rounded_minutes or ticket.minutes or ticket.elapsed_minutes or 0
        try:
            minutes_decimal = Decimal(int(minutes_value))
        except (TypeError, ValueError, InvalidOperation):
            minutes_decimal = Decimal(0)
        if minutes_decimal:
            hours_decimal = minutes_decimal / SIXTY

    rate = _support_rate_for_client(ticket.client_key, table=table)
    if hours_decimal is None or rate is None:
        return None
    return hours_decimal * rate


def _ensure_calculated_fields(ticket: Ticket, *, initialize_invoice: bool = False, client_table: dict | None = None) -> bool:
    amount = _calculate_ticket_amount(ticket, table=client_table)
    formatted = _format_decimal(amount)
    updated = False
    if ticket.calculated_value != formatted:
        ticket.calculated_value = formatted
        updated = True
    if initialize_invoice:
        existing = ticket.invoiced_total
        if not (isinstance(existing, str) and existing.strip()) and formatted is not None:
            ticket.invoiced_total = formatted
            updated = True
    return updated


def _resolve_hardware(db: Session, payload: dict, fallback_id: int | None) -> Hardware | None:
    hw_id = payload.get("hardware_id", fallback_id)
    barcode = payload.get("hardware_barcode")

    for candidate in barcode_aliases(barcode):
        stmt = select(Hardware).where(Hardware.barcode == candidate)
        hw = db.execute(stmt).scalars().first()
        if hw:
            return hw

    if hw_id:
        return db.get(Hardware, hw_id)

    return None


def _apply_time_math(t: Ticket, payload: dict) -> None:
    tz = getattr(settings, "TZ", "America/Chicago")
    start_iso = payload.get("start_iso", t.start_iso)
    end_iso = payload.get("end_iso", t.end_iso)
    base_minutes = compute_minutes(start_iso, end_iso, tz) if start_iso and end_iso else 0
    minutes, rmin, rhours = round_minutes(base_minutes)
    t.elapsed_minutes = base_minutes
    t.minutes = minutes
    t.rounded_minutes = rmin
    t.rounded_hours = rhours


def _apply_hardware_link(db: Session, t: Ticket, payload: dict) -> None:
    """If entry_type is hardware, sync linked hardware details via id or barcode."""
    if payload.get("entry_type", t.entry_type) != "hardware":
        t.hardware_id = None
        t.hardware_description = None
        t.hardware_sales_price = None
        t.hardware_barcode = None
        t.hardware_quantity = None
        return

    hw = _resolve_hardware(db, payload, t.hardware_id)
    desc_override = payload.get("hardware_description")
    if isinstance(desc_override, str):
        desc_override = desc_override.strip() or None
    price_override = payload.get("hardware_sales_price")
    if isinstance(price_override, str):
        price_override = price_override.strip() or None
    barcode_raw = payload.get("hardware_barcode")
    barcode_override = normalize_barcode(barcode_raw) or ((barcode_raw or "").strip() or None)

    if hw:
        t.hardware_id = hw.id
        t.hardware_barcode = hw.barcode
        t.hardware_description = desc_override if desc_override is not None else hw.description
        t.hardware_sales_price = price_override if price_override is not None else hw.sales_price
    else:
        t.hardware_id = None
        t.hardware_barcode = barcode_override
        t.hardware_description = desc_override
        t.hardware_sales_price = price_override

    qty_value = payload.get("hardware_quantity")
    if qty_value is None:
        qty_value = t.hardware_quantity if t.hardware_quantity else 1
    try:
        qty_int = int(qty_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("hardware_quantity must be a positive integer") from exc
    if qty_int <= 0:
        raise ValueError("hardware_quantity must be a positive integer")
    t.hardware_quantity = qty_int


def _apply_client_link(t: Ticket, payload: dict) -> None:
    client_key = payload.get("client_key", t.client_key)
    if not client_key:
        raise ValueError("client_key is required")
    client_name = payload.get("client") or resolve_client_name(client_key)
    if not client_name:
        raise ValueError(f"Unknown client_key '{client_key}'")
    t.client_key = client_key
    t.client = client_name


def create_entry(db: Session, payload: dict) -> Ticket:
    if "client_key" not in payload or not payload["client_key"]:
        raise ValueError("client_key is required")
    invoice_total_value = _normalize_currency_input(payload.get("invoiced_total"))
    t = Ticket(
        client="",  # populated below
        client_key=payload["client_key"],
        start_iso=payload["start_iso"],
        end_iso=payload.get("end_iso"),
        note=payload.get("note"),
        completed=0,
        sent=payload.get("sent", 0) or 0,
        invoice_number=payload.get("invoice_number"),
        invoiced_total=invoice_total_value,
        created_at=payload.get("created_at") or datetime.utcnow().isoformat(timespec="seconds") + "Z",
        entry_type=payload.get("entry_type", "time"),
        hardware_id=payload.get("hardware_id"),
        calculated_value=None,
    )
    _apply_client_link(t, payload)
    _apply_time_math(t, payload)
    _apply_hardware_link(db, t, payload)
    _ensure_calculated_fields(t, initialize_invoice=True)
    db.add(t)
    db.commit()
    db.refresh(t)
    if t.entry_type == "hardware" and t.hardware_id:
        hardware = db.get(Hardware, t.hardware_id)
        unit_sale = _money_to_float(t.hardware_sales_price)
        unit_cost = _money_to_float(hardware.acquisition_cost) if hardware else None
        quantity = t.hardware_quantity or 1
        sale_total = unit_sale * quantity if unit_sale is not None else None
        cost_total = unit_cost * quantity if unit_cost is not None else None
        ensure_ticket_usage_event(
            db,
            ticket_id=t.id,
            hardware_id=t.hardware_id,
            quantity=t.hardware_quantity or 1,
            note=t.note,
            sale_price=sale_total,
            acquisition_cost=cost_total,
        )
    return t


def update_ticket(db: Session, t: Ticket, payload: dict) -> Ticket:
    if "client_key" in payload or "client" in payload:
        _apply_client_link(t, payload)
    data = dict(payload)
    if "invoiced_total" in data:
        data["invoiced_total"] = _normalize_currency_input(data.get("invoiced_total"))
    for k, v in data.items():
        if k in {"client", "client_key"}:
            continue
        if not hasattr(t, k):
            continue
        setattr(t, k, v)
    if any(k in payload for k in ("start_iso", "end_iso")):
        _apply_time_math(t, payload)
    if any(k in payload for k in ("entry_type", "hardware_id", "hardware_barcode", "hardware_quantity", "hardware_sales_price", "hardware_description")):
        _apply_hardware_link(db, t, payload)
    initialize_invoice = not (isinstance(t.invoiced_total, str) and t.invoiced_total.strip())
    _ensure_calculated_fields(t, initialize_invoice=initialize_invoice)
    db.commit()
    db.refresh(t)
    if t.entry_type == "hardware" and t.hardware_id:
        hardware = db.get(Hardware, t.hardware_id)
        unit_sale = _money_to_float(t.hardware_sales_price)
        unit_cost = _money_to_float(hardware.acquisition_cost) if hardware else None
        quantity = t.hardware_quantity or 1
        sale_total = unit_sale * quantity if unit_sale is not None else None
        cost_total = unit_cost * quantity if unit_cost is not None else None
        ensure_ticket_usage_event(
            db,
            ticket_id=t.id,
            hardware_id=t.hardware_id,
            quantity=t.hardware_quantity or 1,
            note=t.note,
            sale_price=sale_total,
            acquisition_cost=cost_total,
        )
    else:
        delete_ticket_event(db, t.id)
    return t


def delete_ticket(db: Session, ticket: Ticket) -> None:
    delete_ticket_event(db, ticket.id)
    db.delete(ticket)
    db.commit()
