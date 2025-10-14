from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class AliasCreate(BaseModel):
    alias: str = Field(..., max_length=128)
    kind: str = Field(default="UPC", max_length=32)
    hardware_id: int

class AliasOut(BaseModel):
    id: int
    alias: str
    kind: str
    hardware_id: int

    class Config:
        from_attributes = True

class ResolveResult(BaseModel):
    hardware_id: int
    barcode: Optional[str] = None
    description: Optional[str] = None
