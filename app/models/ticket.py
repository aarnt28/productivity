from __future__ import annotations
from sqlalchemy import Column, Integer, Text
from ..db.session import Base


class Ticket(Base):
    __tablename__ = "tickets"
    __allow_unmapped__ = True

    id = Column(Integer, primary_key=True, index=True)
    client = Column(Text, nullable=False)
    client_key = Column(Text, nullable=False, index=True)
    start_iso = Column(Text, nullable=False)
    end_iso = Column(Text, nullable=True)
    elapsed_minutes = Column(Integer, nullable=False)
    rounded_minutes = Column(Integer, nullable=False)
    rounded_hours = Column(Text, nullable=False)
    note = Column(Text, nullable=True)
    completed = Column(Integer, nullable=False)
    sent = Column(Integer, nullable=False, default=0)
    invoice_number = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False)
    minutes = Column(Integer, nullable=False, default=0)
    entry_type = Column(Text, nullable=False, default="time")  # 'time' or 'hardware'

    # Link & snapshot when entry_type == 'hardware'
    hardware_id = Column(Integer, nullable=True, index=True)
    hardware_description = Column(Text, nullable=True)
    hardware_sales_price = Column(Text, nullable=True)
    hardware_quantity = Column(Integer, nullable=True, default=1)
    invoiced_total = Column(Text, nullable=True)
    calculated_value = Column(Text, nullable=True)

    @property
    def hardware_barcode(self) -> str | None:
        return getattr(self, "_hardware_barcode", None)

    @hardware_barcode.setter
    def hardware_barcode(self, value: str | None) -> None:
        if value:
            self._hardware_barcode = value
        elif hasattr(self, "_hardware_barcode"):
            delattr(self, "_hardware_barcode")