from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional


class EntryBase(BaseModel):
    client: Optional[str] = None
    client_key: str
    note: Optional[str] = None
    entry_type: str = Field(default="time", pattern="^(time|hardware)$")
    hardware_id: Optional[int] = None  # when entry_type == 'hardware'
    hardware_barcode: Optional[str] = None
    hardware_quantity: Optional[int] = Field(default=None, ge=1)
    hardware_description: Optional[str] = None
    hardware_sales_price: Optional[str] = None


class EntryCreate(EntryBase):
    start_iso: str
    end_iso: Optional[str] = None
    invoice_number: Optional[str] = None
    sent: Optional[int] = 0
    invoiced_total: Optional[str] = None


class EntryUpdate(BaseModel):
    client: Optional[str] = None
    client_key: Optional[str] = None
    start_iso: Optional[str] = None
    end_iso: Optional[str] = None
    note: Optional[str] = None
    completed: Optional[int] = None
    sent: Optional[int] = None
    invoice_number: Optional[str] = None
    invoiced_total: Optional[str] = None
    entry_type: Optional[str] = Field(default=None, pattern="^(time|hardware)$")
    hardware_id: Optional[int] = None
    hardware_barcode: Optional[str] = None
    hardware_quantity: Optional[int] = Field(default=None, ge=1)
    hardware_description: Optional[str] = None
    hardware_sales_price: Optional[str] = None


class EntryOut(BaseModel):
    id: int
    client: str
    client_key: str
    start_iso: str
    end_iso: Optional[str]
    elapsed_minutes: int
    rounded_minutes: int
    rounded_hours: str
    note: Optional[str]
    completed: int
    sent: int
    invoice_number: Optional[str]
    invoiced_total: Optional[str]
    created_at: str
    minutes: int
    entry_type: str
    hardware_id: Optional[int] = None
    hardware_barcode: Optional[str] = None
    hardware_description: Optional[str] = None
    hardware_sales_price: Optional[str] = None
    hardware_quantity: Optional[int] = None
    calculated_value: Optional[str] = None

    class Config:
        from_attributes = True