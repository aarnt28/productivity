from __future__ import annotations
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.sku_alias import SkuAlias
from app.models.hardware import Hardware

def resolve_any_code(db: Session, code: str) -> Optional[Tuple[Hardware, bool]]:
    """
    Try Hardware.barcode first, then SkuAlias.alias.
    Returns (hardware, via_alias) or None.
    """
    code = (code or "").strip()
    if not code:
        return None

    hw = db.scalar(select(Hardware).where(Hardware.barcode == code))
    if hw:
        return hw, False

    alias_row = db.scalar(select(SkuAlias).where(SkuAlias.alias == code))
    if alias_row:
        hw = db.get(Hardware, alias_row.hardware_id)
        if hw:
            return hw, True
    return None
