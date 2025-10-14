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
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


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


class CatalogItem(Base):
    __tablename__ = "catalog_items"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_catalog_items_sku"),
        CheckConstraint("sku <> ''", name="ck_catalog_items_sku_nonempty"),
        CheckConstraint("default_sell_price >= 0", name="ck_catalog_items_sell_price_nonnegative"),
        CheckConstraint("default_cost >= 0", name="ck_catalog_items_cost_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[UnitEnum] = mapped_column(SAEnum(UnitEnum, name="catalog_item_unit"), nullable=False)
    default_sell_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    default_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    tax_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    aliases: Mapped[List["SkuAlias"]] = relationship(
        "SkuAlias", back_populates="catalog_item", cascade="all, delete-orphan"
    )
    flat_tasks: Mapped[List["FlatTask"]] = relationship(
        "FlatTask", back_populates="catalog_item", cascade="all, delete-orphan"
    )
    inventory_lots: Mapped[List["InventoryLot"]] = relationship(
        "InventoryLot", back_populates="catalog_item", cascade="all, delete-orphan"
    )
    stock_ledger_entries: Mapped[List["StockLedger"]] = relationship(
        "StockLedger", back_populates="catalog_item"
    )
    part_usages: Mapped[List["PartUsage"]] = relationship(
        "PartUsage", back_populates="catalog_item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"CatalogItem(id={self.id!r}, sku={self.sku!r}, name={self.name!r})"


class SkuAlias(Base):
    __tablename__ = "sku_aliases"
    __table_args__ = (
        UniqueConstraint("alias", name="uq_sku_aliases_alias"),
        CheckConstraint("alias <> ''", name="ck_sku_aliases_alias_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[AliasKindEnum] = mapped_column(
        SAEnum(AliasKindEnum, name="sku_alias_kind"), nullable=False, default=AliasKindEnum.UPC
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    catalog_item: Mapped[CatalogItem] = relationship("CatalogItem", back_populates="aliases")

    def __repr__(self) -> str:
        return f"SkuAlias(id={self.id!r}, alias={self.alias!r}, kind={self.kind!r})"


class LaborRole(Base):
    __tablename__ = "labor_roles"
    __table_args__ = (UniqueConstraint("name", name="uq_labor_roles_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    bill_rate: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    cost_rate: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    time_entries: Mapped[List["TimeEntry"]] = relationship(
        "TimeEntry", back_populates="labor_role", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"LaborRole(id={self.id!r}, name={self.name!r})"


class FlatTask(Base):
    __tablename__ = "flat_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    default_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    included_parts_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    catalog_item: Mapped[CatalogItem] = relationship("CatalogItem", back_populates="flat_tasks")

    def __repr__(self) -> str:
        return f"FlatTask(id={self.id!r}, catalog_item_id={self.catalog_item_id!r})"


# Late imports to avoid circular references at runtime while keeping type checking happy.
from app.models.inventory import InventoryLot, StockLedger  # noqa: E402  # pylint: disable=wrong-import-position
from app.models.work import PartUsage, TimeEntry  # noqa: E402  # pylint: disable=wrong-import-position
