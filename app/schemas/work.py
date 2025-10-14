from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, condecimal, conint, constr

from app.schemas.catalog import UnitEnum
from app.schemas.inventory import InventoryLedgerEntry


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"


class WorkOrderStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class ClientCreate(BaseModel):
    name: constr(strip_whitespace=True, min_length=1, max_length=255)
    billing_email: Optional[constr(strip_whitespace=True, max_length=255)] = None
    phone: Optional[constr(strip_whitespace=True, max_length=32)] = None
    address: Optional[str] = None


class ClientOut(ClientCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectCreate(BaseModel):
    client_id: int
    name: constr(strip_whitespace=True, min_length=1, max_length=255)
    status: ProjectStatus = ProjectStatus.ACTIVE
    description: Optional[str] = None


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkOrderCreate(BaseModel):
    client_id: int
    project_id: Optional[int] = None
    title: constr(strip_whitespace=True, min_length=1, max_length=255)
    description: Optional[str] = None


class WorkOrderOut(BaseModel):
    id: int
    client_id: int
    project_id: Optional[int]
    title: str
    description: Optional[str]
    status: WorkOrderStatus
    opened_at: datetime
    closed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class TimeEntryStartRequest(BaseModel):
    work_order_id: Optional[int] = None
    client_id: Optional[int] = None
    project_id: Optional[int] = None
    labor_role_id: int
    user_id: Optional[str] = None
    started_at: Optional[datetime] = None
    bill_rate_override: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    cost_rate_override: Optional[condecimal(max_digits=12, decimal_places=2)] = None
    notes: Optional[str] = None
    created_by: Optional[str] = None


class TimeEntryStopRequest(BaseModel):
    time_entry_id: Optional[int] = None
    ended_at: Optional[datetime] = None
    created_by: Optional[str] = None


class TimeEntryOut(BaseModel):
    id: int
    work_order_id: int
    labor_role_id: int
    user_id: Optional[str]
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    minutes: int
    bill_rate_override: Optional[condecimal(max_digits=12, decimal_places=2)]
    cost_rate_override: Optional[condecimal(max_digits=12, decimal_places=2)]
    billable: bool
    notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class PartIssueRequest(BaseModel):
    work_order_id: int
    warehouse_id: int
    alias: constr(strip_whitespace=True, min_length=1, max_length=128)
    qty: condecimal(max_digits=14, decimal_places=4, gt=0)
    barcode_scanned: bool = True
    notes: Optional[str] = None
    created_by: Optional[str] = None


class PartUsageOut(BaseModel):
    id: int
    work_order_id: int
    catalog_item_id: int
    warehouse_id: int
    qty: condecimal(max_digits=14, decimal_places=4)
    unit_cost_resolved: condecimal(max_digits=14, decimal_places=4)
    sell_price_override: Optional[condecimal(max_digits=12, decimal_places=2)]
    total_cost: condecimal(max_digits=14, decimal_places=4)
    sku: str
    name: str
    unit: UnitEnum


class PartIssueResponse(BaseModel):
    usage: PartUsageOut
    ledger_entries: List[InventoryLedgerEntry]
