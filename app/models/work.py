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
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"


class WorkOrderStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOrderBillingState(str, Enum):
    OPEN = "open"
    AWAITING_APPROVAL = "awaiting_approval"
    READY_TO_BILL = "ready_to_bill"
    INVOICED = "invoiced"
    CLOSED = "closed"


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (Index("ix_clients_name_unique", "name", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    projects: Mapped[List["Project"]] = relationship("Project", back_populates="client", cascade="all, delete-orphan")
    work_orders: Mapped[List["WorkOrder"]] = relationship(
        "WorkOrder", back_populates="client", cascade="all, delete-orphan"
    )
    invoices: Mapped[List["Invoice"]] = relationship("Invoice", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"Client(id={self.id!r}, name={self.name!r})"


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (Index("ix_projects_name", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(ProjectStatus, name="project_status"), nullable=False, default=ProjectStatus.ACTIVE
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    client: Mapped[Client] = relationship("Client", back_populates="projects")
    work_orders: Mapped[List["WorkOrder"]] = relationship(
        "WorkOrder", back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Project(id={self.id!r}, name={self.name!r}, status={self.status!r})"


class WorkOrder(Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        Index("ix_work_orders_status", "status"),
        CheckConstraint("title <> ''", name="ck_work_orders_title_nonempty"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[WorkOrderStatus] = mapped_column(
        SAEnum(WorkOrderStatus, name="work_order_status"), nullable=False, default=WorkOrderStatus.OPEN
    )
    billing_state: Mapped[WorkOrderBillingState] = mapped_column(
        SAEnum(WorkOrderBillingState, name="work_order_billing_state"),
        nullable=False,
        default=WorkOrderBillingState.OPEN,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    client: Mapped[Client] = relationship("Client", back_populates="work_orders")
    project: Mapped[Optional[Project]] = relationship("Project", back_populates="work_orders")
    time_entries: Mapped[List["TimeEntry"]] = relationship(
        "TimeEntry", back_populates="work_order", cascade="all, delete-orphan"
    )
    part_usages: Mapped[List["PartUsage"]] = relationship(
        "PartUsage", back_populates="work_order", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"WorkOrder(id={self.id!r}, title={self.title!r}, status={self.status!r})"


class TimeEntry(Base):
    __tablename__ = "time_entries"
    __table_args__ = (
        CheckConstraint("minutes >= 0", name="ck_time_entries_minutes_nonnegative"),
        Index("ix_time_entries_work_order_id", "work_order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False
    )
    labor_role_id: Mapped[int] = mapped_column(
        ForeignKey("labor_roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    bill_rate_override: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    cost_rate_override: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    snap_cost_rate: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    snap_bill_rate: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    write_off_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    work_order: Mapped[WorkOrder] = relationship("WorkOrder", back_populates="time_entries")
    labor_role: Mapped["LaborRole"] = relationship("LaborRole", back_populates="time_entries")
    def __repr__(self) -> str:
        return f"TimeEntry(id={self.id!r}, work_order_id={self.work_order_id!r}, minutes={self.minutes!r})"


class PartUsage(Base):
    __tablename__ = "part_usage"
    __table_args__ = (
        CheckConstraint("qty > 0", name="ck_part_usage_qty_positive"),
        Index("ix_part_usage_work_order_id", "work_order_id"),
        Index("ix_part_usage_catalog_item_id", "catalog_item_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False
    )
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="RESTRICT"), nullable=False
    )
    warehouse_id: Mapped[int] = mapped_column(
        ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    qty: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    sell_price_override: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    unit_cost_resolved: Mapped[Optional[float]] = mapped_column(Numeric(14, 4), nullable=True)
    snap_unit_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 4), nullable=True)
    snap_unit_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    write_off_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    barcode_scanned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    work_order: Mapped[WorkOrder] = relationship("WorkOrder", back_populates="part_usages")
    catalog_item: Mapped["CatalogItem"] = relationship("CatalogItem", back_populates="part_usages")
    warehouse: Mapped["Warehouse"] = relationship("Warehouse", back_populates="part_usages")
    def __repr__(self) -> str:
        return f"PartUsage(id={self.id!r}, work_order_id={self.work_order_id!r}, qty={self.qty!r})"


# Late imports to avoid circular references.
from app.models.catalog import CatalogItem, LaborRole  # noqa: E402  # pylint: disable=wrong-import-position
from app.models.inventory import Warehouse  # noqa: E402  # pylint: disable=wrong-import-position
from app.models.billing import Invoice  # noqa: E402  # pylint: disable=wrong-import-position
