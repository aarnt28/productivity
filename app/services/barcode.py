# app/services/barcode.py
from __future__ import annotations
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import Optional, Tuple

from app.models.sku_alias import SkuAlias
from app.models.hardware import Hardware  # existing model in your repo

def resolve_any_code(db: Session, code: str) -> Optional[Tuple[Hardware, bool]]:
    """
    Try matching a scanned code against Hardware.barcode first (exact),
    then fall back to SkuAlias.alias. Returns (hardware, via_alias: bool) or None.
    """
    code = (code or "").strip()
    if not code:
        return None

    hw = db.scalar(select(Hardware).where(Hardware.barcode == code))
    if hw:
        return hw, False

    alias = db.scalar(select(SkuAlias).where(SkuAlias.alias == code))
    if alias:
        hw = db.get(Hardware, alias.hardware_id)
        if hw:
            return hw, True

    return None
