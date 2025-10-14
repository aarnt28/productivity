from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class InventoryAdjustment(BaseModel):
    hardware_id: Optional[int] = None
    barcode: Optional[str] = None
    quantity: int = Field(gt=0)
    note: Optional[str] = None
    vendor_name: Optional[str] = None
    client_name: Optional[str] = None
    actual_cost: Optional[float] = Field(default=None, ge=0)
    sale_price: Optional[float] = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_target(self) -> "InventoryAdjustment":
        if not self.hardware_id and not (self.barcode and self.barcode.strip()):
            raise ValueError("hardware_id or barcode is required")
        return self


class InventoryEventOut(BaseModel):
    id: int
    hardware_id: int
    change: int
    source: str
    note: Optional[str]
    created_at: str
    ticket_id: Optional[int]
    hardware_barcode: Optional[str] = None
    hardware_description: Optional[str] = None
    counterparty_name: Optional[str] = None
    counterparty_type: Optional[str] = None
    actual_cost: Optional[float] = None
    unit_cost: Optional[float] = None
    sale_price_total: Optional[float] = None
    sale_unit_price: Optional[float] = None
    profit_total: Optional[float] = None
    profit_unit: Optional[float] = None

    class Config:
        from_attributes = True


class InventorySummaryItem(BaseModel):
    hardware_id: int
    barcode: str
    description: str
    quantity: int
    last_activity: Optional[str]
