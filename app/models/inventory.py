from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Float,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class StockReason(str, Enum):
    RECEIPT = "RECEIPT"
    ADJUST = "ADJUST"
    ISSUE = "ISSUE"
    RETURN = "RETURN"


class StockReferenceType(str, Enum):
    WORK_ENTRY = "WorkEntry"
    PURCHASE_ORDER = "PO"
    INIT = "Init"


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = (Index("ix_warehouses_name_unique", "name", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    inventory_lots: Mapped[List["InventoryLot"]] = relationship(
        "InventoryLot", back_populates="warehouse", cascade="all, delete-orphan"
    )
    stock_ledger_entries: Mapped[List["StockLedger"]] = relationship(
        "StockLedger", back_populates="warehouse"
    )
    part_usages: Mapped[List["PartUsage"]] = relationship(
        "PartUsage", back_populates="warehouse"
    )

    def __repr__(self) -> str:
        return f"Warehouse(id={self.id!r}, name={self.name!r})"


class InventoryLot(Base):
    __tablename__ = "inventory_lots"
    __table_args__ = (
        CheckConstraint("qty_on_hand >= 0", name="ck_inventory_lots_qty_nonnegative"),
        Index(
            "ix_inventory_lots_catalog_warehouse",
            "catalog_item_id",
            "warehouse_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    qty_on_hand: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    unit_cost: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    supplier: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    lot_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    catalog_item: Mapped["CatalogItem"] = relationship("CatalogItem", back_populates="inventory_lots")
    warehouse: Mapped[Warehouse] = relationship("Warehouse", back_populates="inventory_lots")
    stock_ledger_entries: Mapped[List["StockLedger"]] = relationship(
        "StockLedger", back_populates="inventory_lot"
    )

    def __repr__(self) -> str:
        return (
            "InventoryLot("
            f"id={self.id!r}, catalog_item_id={self.catalog_item_id!r}, "
            f"warehouse_id={self.warehouse_id!r}, qty_on_hand={self.qty_on_hand!r})"
        )


class StockLedger(Base):
    __tablename__ = "stock_ledger"
    __table_args__ = (
        CheckConstraint("qty_delta <> 0", name="ck_stock_ledger_qty_nonzero"),
        Index("ix_stock_ledger_catalog_item_id", "catalog_item_id"),
        Index("ix_stock_ledger_warehouse_id", "warehouse_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False
    )
    inventory_lot_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("inventory_lots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    qty_delta: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    unit_cost_at_move: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    reason: Mapped[StockReason] = mapped_column(SAEnum(StockReason, name="stock_reason"), nullable=False)
    reference_type: Mapped[StockReferenceType] = mapped_column(
        SAEnum(StockReferenceType, name="stock_reference_type"), nullable=False
    )
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    moved_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    catalog_item: Mapped["CatalogItem"] = relationship("CatalogItem", back_populates="stock_ledger_entries")
    warehouse: Mapped[Warehouse] = relationship("Warehouse", back_populates="stock_ledger_entries")
    inventory_lot: Mapped[Optional[InventoryLot]] = relationship("InventoryLot", back_populates="stock_ledger_entries")

    def __repr__(self) -> str:
        return (
            "StockLedger("
            f"id={self.id!r}, catalog_item_id={self.catalog_item_id!r}, "
            f"qty_delta={self.qty_delta!r}, reason={self.reason!r})"
        )


class InventoryEvent(Base):
    """Legacy inventory event model kept for compatibility with existing UI flows."""

    __tablename__ = "inventory_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    hardware_id: Mapped[int] = mapped_column(ForeignKey("hardware.id"), nullable=False, index=True)
    change: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tickets.id"), nullable=True, index=True)
    counterparty_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counterparty_type: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actual_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sale_price_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sale_unit_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    hardware = relationship("Hardware", lazy="joined")

    @property
    def hardware_barcode(self) -> Optional[str]:
        return self.hardware.barcode if self.hardware else None

    @property
    def hardware_description(self) -> Optional[str]:
        return self.hardware.description if self.hardware else None

    @property
    def profit_total(self) -> Optional[float]:
        if self.sale_price_total is None or self.actual_cost is None:
            return None
        return self.sale_price_total - self.actual_cost

    @property
    def profit_unit(self) -> Optional[float]:
        total = self.profit_total
        if total is None:
            return None
        quantity = abs(self.change)
        if not quantity:
            return None
        return total / quantity


# Late imports to avoid circular references at runtime while keeping type checking happy.
from app.models.catalog import CatalogItem  # noqa: E402  # pylint: disable=wrong-import-position
from app.models.work import PartUsage  # noqa: E402  # pylint: disable=wrong-import-position
