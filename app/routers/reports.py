from __future__ import annotations

from datetime import date as date_cls, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.billing import Invoice, InvoiceLine, InvoiceStatus
from app.models.catalog import CatalogItem
from app.models.inventory import StockLedger, StockReason
from app.models.work import PartUsage, TimeEntry
from app.models.catalog import LaborRole

router = APIRouter(prefix="/api/reports", tags=["reports"], dependencies=[Depends(api_auth)])

CENTRAL_TZ = ZoneInfo("America/Chicago")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _parse_date(date_str: Optional[str]) -> date_cls:
    if not date_str:
        return datetime.now(tz=CENTRAL_TZ).date()
    try:
        return date_cls.fromisoformat(date_str)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD") from exc


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _to_utc_bounds(d: date_cls) -> tuple[datetime, datetime]:
    start_local = datetime.combine(d, time.min, tzinfo=CENTRAL_TZ)
    end_local = datetime.combine(d, time.max, tzinfo=CENTRAL_TZ)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


@router.get("/daily-rollup")
def daily_rollup(date: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    target_date = _parse_date(date)
    start_utc, end_utc = _to_utc_bounds(target_date)

    # Draft revenue from labor
    labor_stmt = (
        select(TimeEntry, LaborRole)
        .join(LaborRole, TimeEntry.labor_role_id == LaborRole.id)
        .where(TimeEntry.billable.is_(True))
        .where(TimeEntry.ended_at.is_not(None))
        .where(TimeEntry.ended_at >= start_utc)
        .where(TimeEntry.ended_at <= end_utc)
    )
    labor_total = Decimal("0")
    for entry, role in db.execute(labor_stmt):
        minutes = Decimal(entry.minutes or 0)
        bill_rate = Decimal(entry.bill_rate_override if entry.bill_rate_override is not None else role.bill_rate or 0)
        hours = minutes / Decimal(60)
        labor_total += hours * bill_rate

    # Draft revenue from parts
    parts_stmt = (
        select(PartUsage, CatalogItem)
        .join(CatalogItem, PartUsage.catalog_item_id == CatalogItem.id)
        .where(PartUsage.created_at >= start_utc)
        .where(PartUsage.created_at <= end_utc)
    )
    part_total = Decimal("0")
    for usage, item in db.execute(parts_stmt):
        qty = Decimal(usage.qty)
        price = Decimal(
            usage.sell_price_override if usage.sell_price_override is not None else item.default_sell_price or 0
        )
        part_total += qty * price

    draft_total = _quantize(labor_total + part_total)

    # Invoiced totals by status
    invoice_stmt = (
        select(
            Invoice.status,
            func.coalesce(func.sum(InvoiceLine.line_total), 0),
        )
        .join(InvoiceLine, InvoiceLine.invoice_id == Invoice.id)
        .where(Invoice.created_at >= start_utc)
        .where(Invoice.created_at <= end_utc)
        .group_by(Invoice.status)
    )
    invoiced_total = Decimal("0")
    paid_total = Decimal("0")
    for status_value, total in db.execute(invoice_stmt):
        total_dec = Decimal(total)
        if status_value in (InvoiceStatus.SENT, InvoiceStatus.PAID):
            invoiced_total += total_dec
        if status_value == InvoiceStatus.PAID:
            paid_total += total_dec

    invoiced_total = _quantize(invoiced_total)
    paid_total = _quantize(paid_total)

    # COGS from stock ledger issues
    cogs_stmt = (
        select(
            func.coalesce(
                func.sum(func.abs(StockLedger.qty_delta) * StockLedger.unit_cost_at_move),
                0,
            )
        )
        .where(StockLedger.reason == StockReason.ISSUE)
        .where(StockLedger.moved_at >= start_utc)
        .where(StockLedger.moved_at <= end_utc)
    )
    cogs_value = Decimal(db.scalar(cogs_stmt) or 0)
    cogs_total = _quantize(cogs_value)

    return {
        "date": target_date.isoformat(),
        "money_generated": {
            "draft": float(draft_total),
            "invoiced": float(invoiced_total),
            "paid": float(paid_total),
        },
        "money_spent": {"cogs": float(cogs_total)},
    }

