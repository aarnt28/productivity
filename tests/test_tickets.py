import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

from app.db.session import Base
from app.crud.tickets import create_entry, list_active_tickets

# Ensure models are registered so metadata tables are created
from app.models import ticket as ticket_model  # noqa: F401


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_list_active_tickets_excludes_hardware_entries(db_session):
    open_time_ticket = create_entry(
        db_session,
        {
            "client_key": "client_a",
            "client": "Client A",
            "start_iso": "2024-01-01T09:00:00",
        },
    )

    # Hardware entries remain open but should not be returned by the active listing
    create_entry(
        db_session,
        {
            "client_key": "client_b",
            "client": "Client B",
            "entry_type": "hardware",
            "hardware_description": "Wireless Access Point",
            "hardware_quantity": 1,
            "hardware_sales_price": "250",
            "start_iso": "2024-01-02T09:00:00",
        },
    )

    closed_time_ticket = create_entry(
        db_session,
        {
            "client_key": "client_c",
            "client": "Client C",
            "start_iso": "2024-01-03T10:00:00",
            "end_iso": "2024-01-03T12:00:00",
        },
    )
    closed_time_ticket.end_iso = "2024-01-03T12:00:00"
    db_session.commit()

    active = list_active_tickets(db_session)

    assert [ticket.id for ticket in active] == [open_time_ticket.id]
