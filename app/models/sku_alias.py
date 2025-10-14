# app/models/sku_alias.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
from app.db.session import Base

# This maps any “alias” (UPC/EAN/MPN/VendorSKU/YourCustomCode) to an existing hardware row.
# We don’t duplicate prices or descriptions here—hardware stays your “catalog” source of truth.

class SkuAlias(Base):
    __tablename__ = "sku_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hardware_id: Mapped[int] = mapped_column(ForeignKey("hardware.id", ondelete="CASCADE"), nullable=False)
    alias: Mapped[str] = mapped_column(String(128), nullable=False)      # the code we scan (UPC/EAN/etc.)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="UPC")  # 'UPC'|'EAN'|'MPN'|'VendorSKU'|'Custom'
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    hardware = relationship("Hardware", backref="aliases")

    __table_args__ = (
        UniqueConstraint("alias", name="uq_sku_aliases_alias"),
    )
