from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, condecimal, constr


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"


class InvoiceLineType(str, Enum):
    LABOR = "labor"
    PART = "part"
    FLAT = "flat"


class InvoiceSourceType(str, Enum):
    TIME_ENTRY = "time_entry"
    PART_USAGE = "part_usage"
    FLAT_TASK = "flat_task"


class InvoiceLineCreate(BaseModel):
    line_type: InvoiceLineType
    description: constr(strip_whitespace=True, min_length=1)
    qty: condecimal(max_digits=12, decimal_places=4)
    unit_price: condecimal(max_digits=12, decimal_places=2)
    source_type: InvoiceSourceType
    source_id: int


class InvoiceCreateRequest(BaseModel):
    client_id: int
    lines: List[InvoiceLineCreate]
    tax: condecimal(max_digits=12, decimal_places=2) = 0
    notes: Optional[str] = None
    created_by: Optional[str] = None


class InvoiceLineOut(BaseModel):
    id: int
    invoice_id: int
    line_type: InvoiceLineType
    description: str
    qty: condecimal(max_digits=12, decimal_places=4)
    unit_price: condecimal(max_digits=12, decimal_places=2)
    line_total: condecimal(max_digits=12, decimal_places=2)
    source_type: InvoiceSourceType
    source_id: Optional[int]

    class Config:
        from_attributes = True


class InvoiceOut(BaseModel):
    id: int
    client_id: int
    status: InvoiceStatus
    subtotal: condecimal(max_digits=12, decimal_places=2)
    tax: condecimal(max_digits=12, decimal_places=2)
    total: condecimal(max_digits=12, decimal_places=2)
    notes: Optional[str]
    created_at: datetime
    created_by: Optional[str]
    lines: List[InvoiceLineOut]

    class Config:
        from_attributes = True


class InvoiceFinalizeRequest(BaseModel):
    status: InvoiceStatus = InvoiceStatus.SENT


class UnbilledTimeItem(BaseModel):
    time_entry_id: int
    work_order_id: int
    client_id: int
    project_id: Optional[int] = None
    minutes: int
    resolved_bill_rate: condecimal(max_digits=12, decimal_places=2)
    resolved_cost_rate: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    subtotal: condecimal(max_digits=12, decimal_places=2)
    description: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    work_order_title: Optional[str] = None


class UnbilledPartItem(BaseModel):
    part_usage_id: int
    work_order_id: int
    client_id: int
    project_id: Optional[int] = None
    catalog_item_id: int
    sku: str
    name: str
    qty: condecimal(max_digits=14, decimal_places=4)
    unit: str
    resolved_sell_price: condecimal(max_digits=12, decimal_places=2)
    resolved_cost: condecimal(max_digits=12, decimal_places=4)
    subtotal: condecimal(max_digits=12, decimal_places=2)
    created_at: datetime
    work_order_title: Optional[str] = None


class UnbilledFlatItem(BaseModel):
    catalog_item_id: int
    work_order_id: Optional[int]
    sku: str
    name: str
    qty: condecimal(max_digits=12, decimal_places=4) = 1
    sell_price: condecimal(max_digits=12, decimal_places=2)


class UnbilledResponse(BaseModel):
    time: List[UnbilledTimeItem]
    parts: List[UnbilledPartItem]
    flat: List[UnbilledFlatItem]
