from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.billing import Invoice, InvoiceLine, InvoiceLineType, InvoiceSourceType, InvoiceStatus
from app.models.catalog import CatalogItem, UnitEnum
from app.models.work import PartUsage, TimeEntry, WorkOrder
from app.models.catalog import LaborRole
from app.schemas.billing import (
    InvoiceCreateRequest,
    InvoiceStatus as InvoiceStatusSchema,
    UnbilledFlatItem,
    UnbilledPartItem,
    UnbilledResponse,
    UnbilledTimeItem,
)
from app.services.costing import compute_invoice_totals, resolve_labor_rates

TWO_PLACES = Decimal("0.01")
FOUR_PLACES = Decimal("0.0001")


class BillingError(RuntimeError):
    pass


def _decimal(value: object, places: Decimal = TWO_PLACES) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(places, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)


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
        select(TimeEntry, WorkOrder, LaborRole)
        .join(WorkOrder, TimeEntry.work_order_id == WorkOrder.id)
        .join(LaborRole, TimeEntry.labor_role_id == LaborRole.id)
        .where(TimeEntry.billable.is_(True))
        .where(TimeEntry.ended_at.is_not(None))
        .where(~TimeEntry.id.in_(subq))
        .order_by(TimeEntry.ended_at.desc())
    )
    if client_id:
        stmt = stmt.where(WorkOrder.client_id == client_id)

    items: List[UnbilledTimeItem] = []
    for entry, work_order, role in db.execute(stmt):
        rates = resolve_labor_rates(
            role,
            bill_rate_override=entry.bill_rate_override,
            cost_rate_override=entry.cost_rate_override,
        )
        hours = Decimal(entry.minutes or 0) / Decimal(60)
        subtotal = (hours * rates.bill_rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        items.append(
            UnbilledTimeItem(
                time_entry_id=entry.id,
                work_order_id=entry.work_order_id,
                client_id=work_order.client_id,
                project_id=work_order.project_id,
                minutes=entry.minutes or 0,
                resolved_bill_rate=rates.bill_rate,
                resolved_cost_rate=rates.cost_rate,
                subtotal=subtotal,
                description=entry.notes,
                started_at=entry.started_at,
                ended_at=entry.ended_at,
                work_order_title=work_order.title,
            )
        )
    return items


def _unbilled_part_usage(db: Session, client_id: Optional[int]) -> List[UnbilledPartItem]:
    subq = select(InvoiceLine.source_id).where(InvoiceLine.source_type == InvoiceSourceType.PART_USAGE)
    stmt = (
        select(PartUsage, WorkOrder, CatalogItem)
        .join(WorkOrder, PartUsage.work_order_id == WorkOrder.id)
        .join(CatalogItem, PartUsage.catalog_item_id == CatalogItem.id)
        .where(~PartUsage.id.in_(subq))
        .order_by(PartUsage.created_at.desc())
    )
    if client_id:
        stmt = stmt.where(WorkOrder.client_id == client_id)

    items: List[UnbilledPartItem] = []
    for usage, work_order, item in db.execute(stmt):
        resolved_price = usage.sell_price_override if usage.sell_price_override is not None else item.default_sell_price or Decimal("0")
        resolved_price = _decimal(resolved_price, TWO_PLACES)
        resolved_cost = _decimal(usage.unit_cost_resolved or Decimal("0"), TWO_PLACES)
        qty = _decimal(usage.qty, FOUR_PLACES)
        subtotal = (resolved_price * qty).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        items.append(
            UnbilledPartItem(
                part_usage_id=usage.id,
                work_order_id=usage.work_order_id,
                client_id=work_order.client_id,
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
            )
        )
    return items


def get_unbilled(db: Session, client_id: Optional[int]) -> UnbilledResponse:
    return UnbilledResponse(
        time=_unbilled_time_entries(db, client_id),
        parts=_unbilled_part_usage(db, client_id),
        flat=_unbilled_flat_items(db, client_id),
    )


def create_invoice(db: Session, payload: InvoiceCreateRequest) -> Invoice:
    if not payload.lines:
        raise BillingError("Cannot create an invoice without lines.")

    subtotal = Decimal("0")
    for line in payload.lines:
        if _already_invoiced(db, InvoiceSourceType(line.source_type), line.source_id):
            raise BillingError(f"Source {line.source_type}:{line.source_id} is already invoiced.")
        qty = _decimal(line.qty, FOUR_PLACES)
        unit_price = _decimal(line.unit_price, TWO_PLACES)
        line_total = qty * unit_price
        subtotal += line_total

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

    for line in payload.lines:
        qty = _decimal(line.qty, FOUR_PLACES)
        unit_price = _decimal(line.unit_price, TWO_PLACES)
        line_total = qty * unit_price
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
            )
        )

    db.flush()
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
