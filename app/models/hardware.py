from __future__ import annotations
from sqlalchemy import Column, Integer, Text
from ..db.session import Base


class Hardware(Base):
    __tablename__ = "hardware"

    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(Text, nullable=False, index=True, unique=True)
    description = Column(Text, nullable=False)
    acquisition_cost = Column(Text, nullable=True)
    sales_price = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False)