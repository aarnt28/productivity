from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from sqlalchemy import (
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


class InvoiceStatus(str, Enum):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"


class InvoiceLineType(str, Enum):
    LABOR = "labor"
    PART = "part"
    FLAT = "flat"


class InvoiceSourceType(str, Enum):
    TIME_ENTRY = "time_entry"
    PART_USAGE = "part_usage"
    FLAT_TASK = "flat_task"


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (Index("ix_invoices_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    status: Mapped[InvoiceStatus] = mapped_column(
        SAEnum(InvoiceStatus, name="invoice_status"), nullable=False, default=InvoiceStatus.DRAFT
    )
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    client: Mapped["Client"] = relationship("Client", back_populates="invoices")
    lines: Mapped[List["InvoiceLine"]] = relationship(
        "InvoiceLine", back_populates="invoice", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"Invoice(id={self.id!r}, client_id={self.client_id!r}, status={self.status!r})"


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (Index("ix_invoice_lines_invoice_id", "invoice_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    line_type: Mapped[InvoiceLineType] = mapped_column(
        SAEnum(InvoiceLineType, name="invoice_line_type"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=1)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    line_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    source_type: Mapped[InvoiceSourceType] = mapped_column(
        SAEnum(InvoiceSourceType, name="invoice_source_type"), nullable=False
    )
    source_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    invoice: Mapped[Invoice] = relationship("Invoice", back_populates="lines")
    def __repr__(self) -> str:
        return (
            "InvoiceLine("
            f"id={self.id!r}, invoice_id={self.invoice_id!r}, line_type={self.line_type!r}, total={self.line_total!r})"
        )

# Late imports to avoid circular references.
from app.models.work import Client  # noqa: E402  # pylint: disable=wrong-import-position
