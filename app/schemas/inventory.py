from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, condecimal, conint, root_validator


class StockReason(str, Enum):
    RECEIPT = "RECEIPT"
    ADJUST = "ADJUST"
    ISSUE = "ISSUE"
    RETURN = "RETURN"


class StockReferenceType(str, Enum):
    WORK_ENTRY = "WorkEntry"
    PURCHASE_ORDER = "PO"
    INIT = "Init"


AmountValue = Decimal | float | int | str


class InventoryAdjustment(BaseModel):
    hardware_id: Optional[int] = Field(None, gt=0)
    barcode: Optional[str] = None
    quantity: conint(gt=0)
    note: Optional[str] = None
    vendor_name: Optional[str] = None
    client_name: Optional[str] = None
    actual_cost: Optional[AmountValue] = None
    sale_price: Optional[AmountValue] = None

    @root_validator
    def _ensure_hardware_identifier(cls, values):
        hardware_id = values.get("hardware_id")
        barcode = values.get("barcode")
        if not hardware_id and not barcode:
            raise ValueError("Either hardware_id or barcode must be provided")
        return values


class InventoryEventOut(BaseModel):
    id: int
    hardware_id: int
    change: int
    source: str
    note: Optional[str] = None
    created_at: str
    ticket_id: Optional[int] = None
    counterparty_name: Optional[str] = None
    counterparty_type: Optional[str] = None
    actual_cost: Optional[float] = None
    unit_cost: Optional[float] = None
    sale_price_total: Optional[float] = None
    sale_unit_price: Optional[float] = None
    hardware_barcode: Optional[str] = None
    hardware_description: Optional[str] = None
    profit_total: Optional[float] = None
    profit_unit: Optional[float] = None

    class Config:
        from_attributes = True


class InventorySummaryItem(BaseModel):
    hardware_id: int
    barcode: Optional[str] = None
    description: Optional[str] = None
    quantity: int
    last_activity: Optional[datetime] = None

    class Config:
        from_attributes = True


class InventoryReceiptLine(BaseModel):
    catalog_item_id: int = Field(..., gt=0)
    qty: condecimal(max_digits=14, decimal_places=4, gt=0)
    unit_cost: condecimal(max_digits=14, decimal_places=4, ge=0)
    supplier: Optional[str] = None
    lot_code: Optional[str] = None


class InventoryReceiptRequest(BaseModel):
    warehouse_id: int = Field(..., gt=0)
    received_at: Optional[datetime] = None
    lines: List[InventoryReceiptLine]

    @classmethod
    def validate_lines(cls, values):
        if not values.get("lines"):
            raise ValueError("At least one line is required")
        return values


class InventoryAdjustLine(BaseModel):
    catalog_item_id: int = Field(..., gt=0)
    qty_delta: condecimal(max_digits=14, decimal_places=4)
    note: Optional[str] = None
    unit_cost: Optional[condecimal(max_digits=14, decimal_places=4)] = None


class InventoryAdjustRequest(BaseModel):
    warehouse_id: int
    reason: StockReason = StockReason.ADJUST
    note: Optional[str] = None
    created_by: Optional[str] = None
    lines: List[InventoryAdjustLine]


class InventoryStockItem(BaseModel):
    catalog_item_id: int
    sku: str
    name: str
    qty_on_hand: condecimal(max_digits=14, decimal_places=4)
    default_unit_cost: Optional[condecimal(max_digits=14, decimal_places=4)] = None
    total_cost: Optional[condecimal(max_digits=14, decimal_places=4)] = None


class InventoryLedgerEntry(BaseModel):
    id: int
    catalog_item_id: int
    warehouse_id: int
    inventory_lot_id: Optional[int]
    qty_delta: condecimal(max_digits=14, decimal_places=4)
    unit_cost_at_move: condecimal(max_digits=14, decimal_places=4)
    reason: StockReason
    reference_type: StockReferenceType
    reference_id: Optional[str]
    moved_at: datetime
    created_by: Optional[str]

    class Config:
        from_attributes = True


class InventoryLotOut(BaseModel):
    id: int
    catalog_item_id: int
    warehouse_id: int
    qty_on_hand: condecimal(max_digits=14, decimal_places=4)
    unit_cost: condecimal(max_digits=14, decimal_places=4)
    received_at: datetime
    supplier: Optional[str]
    lot_code: Optional[str]

    class Config:
        from_attributes = True


class InventoryReceiptResponse(BaseModel):
    warehouse_id: int
    lots: List[InventoryLotOut]
    ledger_entries: List[InventoryLedgerEntry]


class InventoryAdjustResponse(BaseModel):
    warehouse_id: int
    ledger_entries: List[InventoryLedgerEntry]
