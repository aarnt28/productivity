from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing import Invoice, InvoiceLine, InvoiceLineType, InvoiceSourceType, InvoiceStatus
from app.models.catalog import CatalogItem, UnitEnum
from app.models.hardware import Hardware
from app.models.ticket import Ticket
from app.models.work import Client, PartUsage, TimeEntry, WorkOrder
from app.models.catalog import LaborRole
from app.schemas.billing import (
    InvoiceCreateRequest,
    InvoiceStatus as InvoiceStatusSchema,
    UnbilledFlatItem,
    UnbilledPartItem,
    UnbilledResponse,
    UnbilledTimeItem,
)
from app.services.clientsync import load_client_table
from app.services.costing import compute_invoice_totals, resolve_labor_rates

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class BillingError(RuntimeError):
    pass


def _decimal(value: object, places: Decimal = TWO_PLACES) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(places, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)


def _safe_decimal(value: object | None, places: Decimal = TWO_PLACES) -> Decimal:
    if value is None:
        return Decimal("0").quantize(places, rounding=ROUND_HALF_UP)
    try:
        return _decimal(value, places)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0").quantize(places, rounding=ROUND_HALF_UP)


def _decimal_or_none(value: object | None, places: Decimal = TWO_PLACES) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return _decimal(value, places)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _legacy_source_id(source_id: int) -> int:
    return -abs(source_id)


def _already_invoiced(db: Session, source_type: InvoiceSourceType, source_id: int) -> bool:
    return bool(
        db.scalar(
            select(InvoiceLine.id).where(
                InvoiceLine.source_type == source_type,
                InvoiceLine.source_id == source_id,
            )
        )
    )


def _unbilled_time_entries(db: Session, client_id: Optional[int]) -> List[UnbilledTimeItem]:
    subq = select(InvoiceLine.source_id).where(InvoiceLine.source_type == InvoiceSourceType.TIME_ENTRY)

    stmt = (
        select(TimeEntry, WorkOrder, Client, LaborRole)
        .join(WorkOrder, TimeEntry.work_order_id == WorkOrder.id)
        .join(Client, WorkOrder.client_id == Client.id)
        .join(LaborRole, TimeEntry.labor_role_id == LaborRole.id)
        .where(TimeEntry.billable.is_(True))
        .where(TimeEntry.ended_at.is_not(None))
        .where(~TimeEntry.id.in_(subq))
        .order_by(TimeEntry.ended_at.desc())
    )
    if client_id:
        stmt = stmt.where(WorkOrder.client_id == client_id)

    client_table = load_client_table()
    rate_lookup: Dict[str, Tuple[str, Decimal]] = {}
    for key, entry in (client_table or {}).items():
        if not isinstance(entry, dict):
            continue
        support_rate = entry.get("support_rate")
        if support_rate is None:
            continue
        try:
            resolved_rate = _decimal(support_rate, TWO_PLACES)
        except (InvalidOperation, ValueError, TypeError):
            continue
        aliases = {str(key)}
        for alias in (entry.get("name"), entry.get("display_name")):
            if isinstance(alias, str) and alias.strip():
                aliases.add(alias)
        for alias in aliases:
            normalized = alias.strip().casefold()
            if not normalized:
                continue
            rate_lookup[normalized] = (str(key), resolved_rate)

    items: List[UnbilledTimeItem] = []
    for entry, work_order, client, role in db.execute(stmt):
        rates = resolve_labor_rates(
            role,
            bill_rate_override=entry.bill_rate_override,
            cost_rate_override=entry.cost_rate_override,
        )
        client_key = None
        bill_rate = rates.bill_rate
        normalized_name = (client.name or "").strip().casefold()
        if normalized_name and normalized_name in rate_lookup:
            client_key, client_rate = rate_lookup[normalized_name]
            bill_rate = client_rate
        hours = Decimal(entry.minutes or 0) / Decimal(60)
        subtotal = (hours * bill_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        items.append(
            UnbilledTimeItem(
                time_entry_id=entry.id,
                work_order_id=entry.work_order_id,
                client_id=client.id,
                client_name=client.name,
                client_key=client_key,
                project_id=work_order.project_id,
                minutes=entry.minutes or 0,
                resolved_bill_rate=bill_rate,
                resolved_cost_rate=rates.cost_rate,
                subtotal=subtotal,
                description=entry.notes,
                started_at=entry.started_at,
                ended_at=entry.ended_at,
                work_order_title=work_order.title,
                source_type=InvoiceSourceType.TIME_ENTRY.value,
                source_id=entry.id,
                legacy=False,
                ticket_id=None,
            )
        )
    return items


def _unbilled_part_usage(db: Session, client_id: Optional[int]) -> List[UnbilledPartItem]:
    subq = select(InvoiceLine.source_id).where(InvoiceLine.source_type == InvoiceSourceType.PART_USAGE)
    stmt = (
        select(PartUsage, WorkOrder, Client, CatalogItem)
        .join(WorkOrder, PartUsage.work_order_id == WorkOrder.id)
        .join(Client, WorkOrder.client_id == Client.id)
        .join(CatalogItem, PartUsage.catalog_item_id == CatalogItem.id)
        .where(~PartUsage.id.in_(subq))
        .order_by(PartUsage.created_at.desc())
    )
    if client_id:
        stmt = stmt.where(WorkOrder.client_id == client_id)

    items: List[UnbilledPartItem] = []
    for usage, work_order, client, item in db.execute(stmt):
        resolved_price = usage.sell_price_override if usage.sell_price_override is not None else item.default_sell_price or Decimal("0")
        resolved_price = _decimal(resolved_price, TWO_PLACES)
        resolved_cost = _decimal(usage.unit_cost_resolved or Decimal("0"), TWO_PLACES)
        qty = _decimal(usage.qty, FOUR_PLACES)
        subtotal = (resolved_price * qty).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        items.append(
            UnbilledPartItem(
                part_usage_id=usage.id,
                work_order_id=usage.work_order_id,
                client_id=client.id,
                client_name=client.name,
                project_id=work_order.project_id,
                catalog_item_id=usage.catalog_item_id,
                sku=item.sku,
                name=item.name,
                qty=qty,
                unit=item.unit.value if isinstance(item.unit, UnitEnum) else str(item.unit),
                resolved_sell_price=resolved_price,
                resolved_cost=resolved_cost,
                subtotal=subtotal,
                created_at=usage.created_at,
                work_order_title=work_order.title,
                source_type=InvoiceSourceType.PART_USAGE.value,
                source_id=usage.id,
                legacy=False,
                ticket_id=None,
            )
        )
    return items


def _unbilled_flat_items(db: Session, client_id: Optional[int]) -> List[UnbilledFlatItem]:
    stmt = select(CatalogItem).where(CatalogItem.unit == UnitEnum.FLAT, CatalogItem.is_active.is_(True))
    items: List[UnbilledFlatItem] = []
    for item in db.execute(stmt).scalars():
        items.append(
            UnbilledFlatItem(
                catalog_item_id=item.id,
                work_order_id=None,
                sku=item.sku,
                name=item.name,
                sell_price=_decimal(item.default_sell_price or Decimal("0")),
                source_type=InvoiceSourceType.FLAT_TASK.value,
                source_id=item.id,
                legacy=False,
            )
        )
    return items


def _legacy_unbilled_tickets(db: Session, client_id: Optional[int]) -> Tuple[List[UnbilledTimeItem], List[UnbilledPartItem]]:
    client_rows = db.execute(select(Client)).scalars().all()
    client_by_id = {client.id: client for client in client_rows}
    client_by_name = {client.name.casefold(): client for client in client_rows if client.name}

    client_filter_name = None
    if client_id and client_id in client_by_id:
        client_filter_name = client_by_id[client_id].name

    stmt = select(Ticket).where(Ticket.sent == 0)
    if client_filter_name:
        stmt = stmt.where(Ticket.client == client_filter_name)

    tickets = db.execute(stmt).scalars().all()

    time_items: List[UnbilledTimeItem] = []
    part_items: List[UnbilledPartItem] = []

    for ticket in tickets:
        entry_type = (ticket.entry_type or "time").strip().lower()
        client_name = (ticket.client or "").strip() or None
        client_key = (ticket.client_key or "").strip() or None
        client_match = client_by_name.get(client_name.casefold()) if client_name else None
        mapped_client_id = client_match.id if client_match else None

        amount = _safe_decimal(ticket.invoiced_total or ticket.calculated_value, TWO_PLACES)

        if entry_type == "hardware":
            qty_raw = ticket.hardware_quantity or 1
            qty = _safe_decimal(qty_raw, FOUR_PLACES)
            price = _safe_decimal(ticket.hardware_sales_price, TWO_PLACES)
            if qty == Decimal("0"):
                qty = _safe_decimal(1, FOUR_PLACES)
            if price == Decimal("0") and qty != Decimal("0"):
                # fallback to derived price from total
                price = _safe_decimal(amount / qty if qty else amount, TWO_PLACES)

            hardware = db.get(Hardware, ticket.hardware_id) if ticket.hardware_id else None
            name = (ticket.hardware_description or (hardware.description if hardware else None) or "Hardware item").strip()
            sku = (hardware.barcode if hardware and hardware.barcode else None) or f"LEG-{ticket.id}"
            created_at = _parse_iso_datetime(getattr(ticket, "created_at", None)) or datetime.utcnow()

            part_items.append(
                UnbilledPartItem(
                    part_usage_id=ticket.id,
                    work_order_id=None,
                    client_id=mapped_client_id,
                    client_name=client_name,
                    client_key=client_key,
                    project_id=None,
                    catalog_item_id=hardware.id if hardware else None,
                    sku=sku,
                    name=name,
                    qty=qty,
                    unit="ea",
                    resolved_sell_price=price,
                    resolved_cost=_safe_decimal(None, TWO_PLACES),
                    subtotal=amount,
                    created_at=created_at,
                    work_order_title=None,
                    source_type=InvoiceSourceType.PART_USAGE.value,
                    source_id=_legacy_source_id(ticket.id),
                    legacy=True,
                    ticket_id=ticket.id,
                )
            )
            continue

        minutes_value = ticket.rounded_minutes or ticket.minutes or ticket.elapsed_minutes or 0
        minutes = int(minutes_value or 0)
        hours = Decimal(minutes) / Decimal(60) if minutes else Decimal("0")
        rate = amount
        if hours:
            try:
                rate = (amount / hours).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            except (InvalidOperation, ZeroDivisionError):
                rate = amount

        time_items.append(
            UnbilledTimeItem(
                time_entry_id=ticket.id,
                work_order_id=None,
                client_id=mapped_client_id,
                client_name=client_name,
                client_key=client_key,
                project_id=None,
                minutes=minutes,
                resolved_bill_rate=_safe_decimal(rate, TWO_PLACES),
                resolved_cost_rate=None,
                subtotal=amount,
                description=(ticket.note or "").strip() or f"Ticket #{ticket.id}",
                started_at=_parse_iso_datetime(getattr(ticket, "start_iso", None)),
                ended_at=_parse_iso_datetime(getattr(ticket, "end_iso", None)),
                work_order_title=None,
                source_type=InvoiceSourceType.TIME_ENTRY.value,
                source_id=_legacy_source_id(ticket.id),
                legacy=True,
                ticket_id=ticket.id,
            )
        )

    return time_items, part_items


def get_unbilled(db: Session, client_id: Optional[int]) -> UnbilledResponse:
    time_entries = _unbilled_time_entries(db, client_id)
    part_usage = _unbilled_part_usage(db, client_id)
    legacy_time, legacy_parts = _legacy_unbilled_tickets(db, client_id)

    combined_time = time_entries + legacy_time
    combined_parts = part_usage + legacy_parts

    combined_time.sort(
        key=lambda item: item.ended_at or item.started_at or datetime.min,
        reverse=True,
    )
    combined_parts.sort(
        key=lambda item: item.created_at,
        reverse=True,
    )

    return UnbilledResponse(
        time=combined_time,
        parts=combined_parts,
        flat=_unbilled_flat_items(db, client_id),
    )


def create_invoice(db: Session, payload: InvoiceCreateRequest) -> Invoice:
    if not payload.lines:
        raise BillingError("Cannot create an invoice without lines.")

    subtotal = Decimal("0")
    legacy_ticket_ids: set[int] = set()
    prepared_lines: List[dict] = []
    for line in payload.lines:
        source_type = InvoiceSourceType(line.source_type)
        source_id = line.source_id
        if source_id is not None and _already_invoiced(db, source_type, source_id):
            raise BillingError(f"Source {line.source_type}:{line.source_id} is already invoiced.")
        if source_id is not None and source_id < 0 and source_type in {
            InvoiceSourceType.TIME_ENTRY,
            InvoiceSourceType.PART_USAGE,
        }:
            legacy_ticket_ids.add(abs(source_id))
        qty = _decimal(line.qty, FOUR_PLACES)
        unit_price = _decimal(line.unit_price, TWO_PLACES)
        unit_cost = _decimal_or_none(line.unit_cost, FOUR_PLACES)
        tax_code = line.tax_code
        snapshot_payload = line.snapshot_json

        if source_type == InvoiceSourceType.TIME_ENTRY:
            entry = db.get(TimeEntry, source_id) if source_id else None
            if not entry:
                raise BillingError("Time entry source missing")
            rates = resolve_labor_rates(
                entry.labor_role,
                bill_rate_override=entry.bill_rate_override,
                cost_rate_override=entry.cost_rate_override,
            )
            resolved_cost = _decimal(rates.cost_rate, TWO_PLACES)
            resolved_bill = unit_price
            entry.snap_cost_rate = resolved_cost
            entry.snap_bill_rate = resolved_bill
            entry.write_off_amount = _decimal(entry.write_off_amount or Decimal("0"))
            if not entry.approved_at:
                entry.approved_at = datetime.utcnow()
            db.add(entry)
            unit_cost = unit_cost or resolved_cost
            if snapshot_payload is None:
                snapshot_payload = json.dumps(
                    {
                        "type": "labor",
                        "time_entry_id": entry.id,
                        "work_order_id": entry.work_order_id,
                        "minutes": entry.minutes,
                        "resolved_bill_rate": str(resolved_bill),
                        "resolved_cost_rate": str(resolved_cost),
                        "notes": entry.notes,
                    }
                )
        elif source_type == InvoiceSourceType.PART_USAGE:
            usage = db.get(PartUsage, source_id) if source_id else None
            if not usage:
                raise BillingError("Part usage source missing")
            resolved_cost_source = (
                usage.snap_unit_cost if usage.snap_unit_cost is not None else usage.unit_cost_resolved or Decimal("0")
            )
            resolved_cost = _decimal(resolved_cost_source, FOUR_PLACES)
            usage.snap_unit_cost = resolved_cost
            usage.snap_unit_price = unit_price
            usage.write_off_amount = _decimal(usage.write_off_amount or Decimal("0"))
            db.add(usage)
            unit_cost = unit_cost or resolved_cost
            if snapshot_payload is None:
                snapshot_payload = json.dumps(
                    {
                        "type": "part",
                        "part_usage_id": usage.id,
                        "work_order_id": usage.work_order_id,
                        "catalog_item_id": usage.catalog_item_id,
                        "qty": str(qty),
                        "unit_price": str(unit_price),
                        "unit_cost": str(resolved_cost),
                    }
                )
        elif source_type == InvoiceSourceType.FLAT_TASK:
            if snapshot_payload is None:
                snapshot_payload = json.dumps(
                    {
                        "type": "flat",
                        "source_id": source_id,
                        "qty": str(qty),
                        "unit_price": str(unit_price),
                    }
                )

        if snapshot_payload is not None and isinstance(snapshot_payload, dict):
            snapshot_payload = json.dumps(snapshot_payload)

        line_total = qty * unit_price
        subtotal += line_total
        prepared_lines.append(
            {
                "line": line,
                "qty": qty,
                "unit_price": unit_price,
                "unit_cost": unit_cost,
                "line_total": line_total,
                "tax_code": tax_code,
                "snapshot": snapshot_payload,
            }
        )

    tax = _decimal(payload.tax)
    total = compute_invoice_totals(subtotal.quantize(TWO_PLACES, rounding=ROUND_HALF_UP), tax)

    invoice = Invoice(
        client_id=payload.client_id,
        status=InvoiceStatus.DRAFT,
        subtotal=subtotal.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
        tax=tax,
        total=total,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    db.add(invoice)
    db.flush()

    for prepared in prepared_lines:
        line = prepared["line"]
        qty = prepared["qty"]
        unit_price = prepared["unit_price"]
        unit_cost = prepared["unit_cost"]
        line_total = prepared["line_total"]
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                line_type=InvoiceLineType(line.line_type),
                description=line.description,
                qty=qty,
                unit_price=unit_price,
                line_total=line_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
                source_type=InvoiceSourceType(line.source_type),
                source_id=line.source_id,
                unit_cost=unit_cost,
                tax_code=prepared["tax_code"],
                snapshot_json=prepared["snapshot"],
            )
        )

    db.flush()
    if legacy_ticket_ids:
        tickets = db.execute(select(Ticket).where(Ticket.id.in_(legacy_ticket_ids))).scalars().all()
        for ticket in tickets:
            ticket.sent = 1
            if not (ticket.invoice_number or "").strip():
                ticket.invoice_number = f"INV-{invoice.id}"
            db.add(ticket)
    db.refresh(invoice)
    return invoice


def finalize_invoice(db: Session, invoice: Invoice, status: InvoiceStatusSchema) -> Invoice:
    if status not in {InvoiceStatusSchema.SENT, InvoiceStatusSchema.PAID}:
        raise BillingError("Finalize expects status sent or paid.")
    invoice.status = InvoiceStatus(status.value)
    db.add(invoice)
    db.flush()
    db.refresh(invoice)
    return invoice
