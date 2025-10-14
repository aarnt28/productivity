from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..models.inventory import InventoryEvent
from ..models.hardware import Hardware


def list_inventory_events(db: Session, limit: int = 100, offset: int = 0) -> list[InventoryEvent]:
    stmt = (
        select(InventoryEvent)
        .order_by(desc(InventoryEvent.created_at), desc(InventoryEvent.id))
        .limit(limit)
        .offset(offset)
    )
    return db.execute(stmt).scalars().all()


def get_inventory_summary(db: Session) -> list[dict[str, object]]:
    stmt = (
        select(
            InventoryEvent.hardware_id,
            Hardware.barcode,
            Hardware.description,
            func.coalesce(func.sum(InventoryEvent.change), 0).label("quantity"),
            func.max(InventoryEvent.created_at).label("last_activity"),
        )
        .join(Hardware, Hardware.id == InventoryEvent.hardware_id)
        .group_by(InventoryEvent.hardware_id, Hardware.barcode, Hardware.description)
        .order_by(Hardware.description)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "hardware_id": row.hardware_id,
            "barcode": row.barcode,
            "description": row.description,
            "quantity": int(row.quantity or 0),
            "last_activity": row.last_activity,
        }
        for row in rows
    ]


def _normalize_amount(value: object) -> float | None:
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


def _unit_value(total: float | None, change: int) -> float | None:
    if total is None:
        return None
    quantity = abs(change)
    if not quantity:
        return None
    return total / quantity


def record_inventory_event(
    db: Session,
    *,
    hardware_id: int,
    change: int,
    source: str = "manual",
    note: str | None = None,
    ticket_id: int | None = None,
    counterparty_name: str | None = None,
    counterparty_type: str | None = None,
    actual_cost: float | None = None,
    sale_price: float | None = None,
) -> InventoryEvent:
    if not change:
        raise ValueError("change must be non-zero")
    name = (counterparty_name or "").strip() or None
    ctype = (counterparty_type or "").strip() or None
    cost_total = _normalize_amount(actual_cost)
    sale_total = _normalize_amount(sale_price)
    unit_cost = _unit_value(cost_total, change)
    unit_sale = _unit_value(sale_total, change)
    event = InventoryEvent(
        hardware_id=hardware_id,
        change=change,
        source=source,
        note=note,
        ticket_id=ticket_id,
        created_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        counterparty_name=name,
        counterparty_type=ctype,
        actual_cost=cost_total,
        unit_cost=unit_cost,
        sale_price_total=sale_total,
        sale_unit_price=unit_sale,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def get_event_by_ticket(db: Session, ticket_id: int) -> InventoryEvent | None:
    stmt = select(InventoryEvent).where(InventoryEvent.ticket_id == ticket_id)
    return db.execute(stmt).scalars().first()


def delete_event(db: Session, event: InventoryEvent) -> None:
    db.delete(event)
    db.commit()


def delete_ticket_event(db: Session, ticket_id: int) -> None:
    existing = get_event_by_ticket(db, ticket_id)
    if existing:
        delete_event(db, existing)


def ensure_ticket_usage_event(
    db: Session,
    *,
    ticket_id: int,
    hardware_id: int,
    quantity: int = 1,
    note: str | None = None,
    sale_price: object | None = None,
    acquisition_cost: object | None = None,
) -> InventoryEvent:
    """Create or update the inventory event associated with a hardware ticket.

    ``quantity`` represents how many units were consumed by the ticket. The
    stored change is always negative to reflect usage.
    """

    change = -abs(quantity)
    existing = get_event_by_ticket(db, ticket_id)
    sale_total = _normalize_amount(sale_price)
    cost_total = _normalize_amount(acquisition_cost)
    unit_cost = _unit_value(cost_total, change)
    unit_sale = _unit_value(sale_total, change)

    if existing:
        existing.hardware_id = hardware_id
        existing.change = change
        existing.source = "ticket"
        existing.note = note
        existing.counterparty_name = None
        existing.counterparty_type = None
        existing.actual_cost = cost_total
        existing.unit_cost = unit_cost
        existing.sale_price_total = sale_total
        existing.sale_unit_price = unit_sale
        db.commit()
        db.refresh(existing)
        return existing

    return record_inventory_event(
        db,
        hardware_id=hardware_id,
        change=change,
        source="ticket",
        note=note,
        ticket_id=ticket_id,
        counterparty_name=None,
        counterparty_type=None,
        actual_cost=cost_total,
        sale_price=sale_total,
    )
