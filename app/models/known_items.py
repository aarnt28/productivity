from __future__ import annotations
from sqlalchemy import Column, Integer, Text
from ..db.session import Base

class known_item(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    barcode = Column(Integer, nullable=False, index=True)
    description = Column(Text, nullable=False, index=True)
    category = Column(Text, nullable=False)
    added_date = Column(Text, nullable=False, index=True)
    
