from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, ForeignKey, UniqueConstraint
from app.db.session import Base

class SkuAlias(Base):
    __tablename__ = "sku_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hardware_id: Mapped[int] = mapped_column(
        ForeignKey("hardware.id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="UPC")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    hardware = relationship("Hardware", backref="aliases")

    __table_args__ = (UniqueConstraint("alias", name="uq_sku_aliases_alias"),)
