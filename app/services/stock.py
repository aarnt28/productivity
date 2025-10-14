from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.catalog import CatalogItem
from app.models.inventory import (
    InventoryLot,
    StockLedger,
    StockReason,
    StockReferenceType,
    Warehouse,
)

FOUR_PLACES = Decimal("0.0001")
TWO_PLACES = Decimal("0.01")


def _as_decimal(value: object, quant: Decimal = FOUR_PLACES) -> Decimal:
    if isinstance(value, Decimal):
        result = value
    else:
        result = Decimal(str(value))
    return result.quantize(quant, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class ReceiptLineResult:
    lot: InventoryLot
    ledger_entry: StockLedger


@dataclass(slots=True)
class IssueResult:
    ledger_entries: List[StockLedger]
    total_qty: Decimal
    total_cost: Decimal

    @property
    def average_cost(self) -> Decimal:
        if self.total_qty == 0:
            return Decimal("0")
        return (self.total_cost / self.total_qty).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


class StockError(RuntimeError):
    pass


def receive_inventory(
    db: Session,
    *,
    warehouse: Warehouse,
    catalog_item: CatalogItem,
    qty: Decimal,
    unit_cost: Decimal,
    received_at: Optional[datetime] = None,
    supplier: Optional[str] = None,
    lot_code: Optional[str] = None,
    created_by: Optional[str] = None,
    reference_type: StockReferenceType = StockReferenceType.PURCHASE_ORDER,
    reference_id: Optional[str] = None,
    reason: StockReason = StockReason.RECEIPT,
) -> ReceiptLineResult:
    qty = _as_decimal(qty)
    unit_cost = _as_decimal(unit_cost)
    if qty <= 0:
        raise StockError("Receipt quantity must be positive.")

    lot = InventoryLot(
        catalog_item_id=catalog_item.id,
        warehouse_id=warehouse.id,
        qty_on_hand=qty,
        unit_cost=unit_cost,
        received_at=received_at or datetime.utcnow(),
        supplier=supplier,
        lot_code=lot_code,
    )
    db.add(lot)
    db.flush()

    ledger = StockLedger(
        catalog_item_id=catalog_item.id,
        warehouse_id=warehouse.id,
        inventory_lot_id=lot.id,
        qty_delta=qty,
        unit_cost_at_move=unit_cost,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        moved_at=received_at or datetime.utcnow(),
        created_by=created_by,
    )
    db.add(ledger)
    db.flush()
    return ReceiptLineResult(lot=lot, ledger_entry=ledger)


def adjust_inventory(
    db: Session,
    *,
    lot: InventoryLot,
    qty_delta: Decimal,
    reason: StockReason = StockReason.ADJUST,
    created_by: Optional[str] = None,
    reference_type: StockReferenceType = StockReferenceType.INIT,
    reference_id: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> StockLedger:
    qty_delta = _as_decimal(qty_delta)
    new_qty = _as_decimal(lot.qty_on_hand) + qty_delta
    if new_qty < 0:
        raise StockError("Adjustment would drive lot negative; use ISSUE.")
    lot.qty_on_hand = new_qty
    ledger = StockLedger(
        catalog_item_id=lot.catalog_item_id,
        warehouse_id=lot.warehouse_id,
        inventory_lot_id=lot.id,
        qty_delta=qty_delta,
        unit_cost_at_move=lot.unit_cost,
        reason=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        moved_at=moved_at or datetime.utcnow(),
        created_by=created_by,
    )
    db.add(ledger)
    db.flush()
    return ledger


def issue_fifo(
    db: Session,
    *,
    warehouse: Warehouse,
    catalog_item: CatalogItem,
    qty: Decimal,
    reason: StockReason = StockReason.ISSUE,
    reference_type: StockReferenceType,
    reference_id: Optional[str],
    created_by: Optional[str] = None,
    moved_at: Optional[datetime] = None,
) -> IssueResult:
    qty = _as_decimal(qty)
    if qty <= 0:
        raise StockError("Issue quantity must be positive.")

    stmt = (
        select(InventoryLot)
        .where(
            InventoryLot.catalog_item_id == catalog_item.id,
            InventoryLot.warehouse_id == warehouse.id,
        )
        .order_by(InventoryLot.received_at.asc(), InventoryLot.id.asc())
    )
    bind = db.get_bind()
    if bind and getattr(bind.dialect, "supports_for_update", False):
        stmt = stmt.with_for_update()

    lots = db.execute(stmt).scalars().all()

    remaining = qty
    total_cost = Decimal("0")
    ledger_entries: List[StockLedger] = []
    timestamp = moved_at or datetime.utcnow()

    for lot in lots:
        if remaining <= 0:
            break
        available = _as_decimal(lot.qty_on_hand)
        if available <= 0:
            continue
        take = min(available, remaining)
        lot.qty_on_hand = (available - take).quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)
        ledger = StockLedger(
            catalog_item_id=catalog_item.id,
            warehouse_id=warehouse.id,
            inventory_lot_id=lot.id,
            qty_delta=-take,
            unit_cost_at_move=_as_decimal(lot.unit_cost),
            reason=reason,
            reference_type=reference_type,
            reference_id=reference_id,
            moved_at=timestamp,
            created_by=created_by,
        )
        db.add(ledger)
        db.flush()
        ledger_entries.append(ledger)
        total_cost += _as_decimal(lot.unit_cost) * take
        remaining -= take

    if remaining > 0:
        raise StockError(
            f"Insufficient stock for catalog_item={catalog_item.sku} in warehouse={warehouse.name}; short {remaining}"
        )

    return IssueResult(
        ledger_entries=ledger_entries,
        total_qty=qty,
        total_cost=total_cost.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP),
    )

