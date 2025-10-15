from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.catalog import CatalogItem
from app.models.inventory import InventoryLot, StockLedger, StockReason, StockReferenceType, Warehouse
from app.schemas.inventory import (
    InventoryAdjustRequest,
    InventoryAdjustResponse,
    InventoryLedgerEntry,
    InventoryReceiptRequest,
    InventoryReceiptResponse,
    InventoryStockItem,
)
from app.services.stock import IssueResult, StockError, issue_fifo, receive_inventory as stock_receive_inventory


router = APIRouter(prefix="/api/v2/inventory", tags=["inventory"], dependencies=[Depends(api_auth)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_warehouse(db: Session, warehouse_id: int) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse


def _ensure_catalog_item(db: Session, item_id: int) -> CatalogItem:
    item = db.get(CatalogItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail=f"Catalog item {item_id} not found")
    return item


@router.post("/receipt", response_model=InventoryReceiptResponse, status_code=status.HTTP_201_CREATED)
def receive_inventory(payload: InventoryReceiptRequest, db: Session = Depends(get_db)):
    warehouse = _ensure_warehouse(db, payload.warehouse_id)
    lots = []
    ledger_entries = []
    for line in payload.lines:
        item = _ensure_catalog_item(db, line.catalog_item_id)
        result = stock_receive_inventory(
            db,
            warehouse=warehouse,
            catalog_item=item,
            qty=Decimal(line.qty),
            unit_cost=Decimal(line.unit_cost),
            received_at=payload.received_at,
            supplier=line.supplier,
            lot_code=line.lot_code,
            created_by=None,
            reference_type=StockReferenceType.PURCHASE_ORDER,
            reference_id=line.lot_code,
            reason=StockReason.RECEIPT,
        )
        lots.append(result.lot)
        ledger_entries.append(result.ledger_entry)
    db.commit()
    for lot in lots:
        db.refresh(lot)
    for entry in ledger_entries:
        db.refresh(entry)
    return InventoryReceiptResponse(warehouse_id=warehouse.id, lots=lots, ledger_entries=ledger_entries)


@router.post("/adjust", response_model=InventoryAdjustResponse)
def adjust_inventory(payload: InventoryAdjustRequest, db: Session = Depends(get_db)):
    warehouse = _ensure_warehouse(db, payload.warehouse_id)
    ledger_entries = []
    for line in payload.lines:
        item = _ensure_catalog_item(db, line.catalog_item_id)
        qty_delta = Decimal(line.qty_delta)
        if qty_delta == 0:
            continue
        if qty_delta > 0:
            result = stock_receive_inventory(
                db,
                warehouse=warehouse,
                catalog_item=item,
                qty=qty_delta,
                unit_cost=Decimal(line.unit_cost or 0),
                supplier="Adjustment",
                lot_code=None,
                created_by=payload.created_by,
                reference_type=StockReferenceType.INIT,
                reference_id="ADJUST+",
                reason=StockReason.ADJUST,
            )
            ledger_entries.append(result.ledger_entry)
        else:
            try:
                issue_result = issue_fifo(
                    db,
                    warehouse=warehouse,
                    catalog_item=item,
                    qty=abs(qty_delta),
                    reason=StockReason.ADJUST,
                    reference_type=StockReferenceType.INIT,
                    reference_id="ADJUST-",
                    created_by=payload.created_by,
                )
                ledger_entries.extend(issue_result.ledger_entries)
            except StockError as exc:
                db.rollback()
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    db.commit()
    for entry in ledger_entries:
        db.refresh(entry)
    return InventoryAdjustResponse(warehouse_id=warehouse.id, ledger_entries=ledger_entries)


@router.get("/stock", response_model=List[InventoryStockItem])
def stock_snapshot(
    warehouse_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
):
    _ensure_warehouse(db, warehouse_id)
    stmt = (
        select(
            InventoryLot.catalog_item_id,
            CatalogItem.sku,
            CatalogItem.name,
            func.coalesce(func.sum(InventoryLot.qty_on_hand), 0),
            CatalogItem.default_cost,
            func.coalesce(func.sum(InventoryLot.qty_on_hand * InventoryLot.unit_cost), 0),
        )
        .join(CatalogItem, CatalogItem.id == InventoryLot.catalog_item_id)
        .where(InventoryLot.warehouse_id == warehouse_id)
        .group_by(
            InventoryLot.catalog_item_id,
            CatalogItem.sku,
            CatalogItem.name,
            CatalogItem.default_cost,
        )
        .order_by(CatalogItem.name.asc())
    )
    rows = db.execute(stmt).all()
    items = []
    for catalog_item_id, sku, name, qty_on_hand, default_cost, total_cost in rows:
        items.append(
            InventoryStockItem(
                catalog_item_id=catalog_item_id,
                sku=sku,
                name=name,
                qty_on_hand=qty_on_hand,
                default_unit_cost=default_cost,
                total_cost=total_cost,
            )
        )
    return items


@router.get("/ledger", response_model=List[InventoryLedgerEntry])
def inventory_ledger(
    from_dt: Optional[str] = Query(default=None, alias="from"),
    to_dt: Optional[str] = Query(default=None, alias="to"),
    warehouse_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
):
    stmt = select(StockLedger)
    if warehouse_id:
        stmt = stmt.where(StockLedger.warehouse_id == warehouse_id)
    if from_dt:
        try:
            start = datetime.fromisoformat(from_dt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid from datetime") from exc
        stmt = stmt.where(StockLedger.moved_at >= start)
    if to_dt:
        try:
            end = datetime.fromisoformat(to_dt)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid to datetime") from exc
        stmt = stmt.where(StockLedger.moved_at <= end)
    stmt = stmt.order_by(StockLedger.moved_at.desc(), StockLedger.id.desc())
    rows = db.execute(stmt).scalars().all()
    return rows


