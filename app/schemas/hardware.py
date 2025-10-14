from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class HardwareBase(BaseModel):
    barcode: str
    description: str
    acquisition_cost: Optional[str] = None
    sales_price: Optional[str] = None


class HardwareCreate(HardwareBase):
    pass


class HardwareUpdate(BaseModel):
    barcode: Optional[str] = None
    description: Optional[str] = None
    acquisition_cost: Optional[str] = None
    sales_price: Optional[str] = None


class HardwareOut(BaseModel):
    id: int
    barcode: str
    description: str
    acquisition_cost: Optional[str]
    sales_price: Optional[str]
    created_at: str
    common_vendors: list[str] = Field(default_factory=list)
    average_unit_cost: Optional[float] = None

    class Config:
        from_attributes = True