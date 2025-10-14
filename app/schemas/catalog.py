from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, condecimal, constr


class UnitEnum(str, Enum):
    EA = "ea"
    HOUR = "hour"
    FT = "ft"
    FLAT = "flat"


class AliasKindEnum(str, Enum):
    UPC = "UPC"
    EAN = "EAN"
    MPN = "MPN"
    VENDOR_SKU = "VendorSKU"


class CatalogItemBase(BaseModel):
    sku: constr(strip_whitespace=True, min_length=1, max_length=64)
    name: constr(strip_whitespace=True, min_length=1, max_length=255)
    description: Optional[str] = None
    unit: UnitEnum = UnitEnum.EA
    default_sell_price: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    default_cost: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    tax_category: Optional[constr(strip_whitespace=True, max_length=64)] = None
    is_active: bool = True


class CatalogItemCreate(CatalogItemBase):
    pass


class CatalogItemUpdate(BaseModel):
    name: Optional[constr(strip_whitespace=True, min_length=1, max_length=255)] = None
    description: Optional[str] = None
    unit: Optional[UnitEnum] = None
    default_sell_price: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    default_cost: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    tax_category: Optional[constr(strip_whitespace=True, max_length=64)] = None
    is_active: Optional[bool] = None


class CatalogItemOut(CatalogItemBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AliasCreate(BaseModel):
    alias: constr(strip_whitespace=True, min_length=1, max_length=128)
    kind: AliasKindEnum = AliasKindEnum.UPC
    catalog_item_id: int


class AliasOut(BaseModel):
    id: int
    catalog_item_id: int
    alias: str
    kind: AliasKindEnum
    created_at: datetime

    class Config:
        from_attributes = True


class CatalogItemSummary(BaseModel):
    id: int
    sku: str
    name: str
    description: Optional[str] = None

    class Config:
        from_attributes = True


class ResolveResult(BaseModel):
    catalog_item_id: int
    sku: str
    name: str

