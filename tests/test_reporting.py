import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATA_DIR", str(ROOT / "data"))

from app.db.session import Base
from app.crud.tickets import create_entry, update_ticket
from app.services.reporting import calculate_ticket_metrics

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


def test_calculate_ticket_metrics_aggregates_revenue(db_session):
    time_ticket_a = create_entry(
        db_session,
        {
            "client_key": "client_a",
            "client": "Client A",
            "start_iso": "2024-01-01T09:00:00",
            "end_iso": "2024-01-01T11:00:00",
        },
    )
    update_ticket(db_session, time_ticket_a, {"completed": 1})

    time_ticket_b = create_entry(
        db_session,
        {
            "client_key": "client_b",
            "client": "Client B",
            "start_iso": "2024-01-02T09:00:00",
            "end_iso": "2024-01-02T10:30:00",
        },
    )
    update_ticket(db_session, time_ticket_b, {"completed": 1, "sent": 1})

    hardware_ticket = create_entry(
        db_session,
        {
            "client_key": "client_a",
            "client": "Client A",
            "entry_type": "hardware",
            "hardware_description": "Firewall Appliance",
            "hardware_sales_price": "500",
            "hardware_quantity": 2,
            "start_iso": "2024-01-05T09:00:00",
            "end_iso": "2024-01-05T09:00:00",
        },
    )

    metrics = calculate_ticket_metrics(
        db_session,
        client_table={
            "client_a": {"name": "Client A", "support_rate": 150},
            "client_b": {"name": "Client B", "support_rate": 200},
        },
    )

    assert metrics["totals"]["revenue_time"] == Decimal("600.00")
    assert metrics["totals"]["revenue_hardware"] == Decimal("1000.00")
    assert metrics["totals"]["revenue_total"] == Decimal("1600.00")
    assert metrics["totals"]["time_ticket_count"] == 2
    assert metrics["totals"]["hardware_ticket_count"] == 1
    assert metrics["totals"]["tickets_open"] == 1  # hardware ticket remains open by default
    assert metrics["totals"]["tickets_completed"] == 2
    assert metrics["totals"]["billable_hours"] == pytest.approx(3.5)
    assert metrics["totals"]["unsent_revenue"] == Decimal("1300.00")
    assert metrics["totals"]["unsent_ticket_count"] == 2

    tickets_by_client = metrics["tickets_by_client"]
    assert tickets_by_client[0]["client"] == "Client A"
    assert tickets_by_client[0]["total"] == 2
    assert tickets_by_client[0]["hardware"] == 1

    revenue_by_client = metrics["revenue_by_client"]
    assert revenue_by_client[0]["client"] == "Client A"
    assert revenue_by_client[0]["total_revenue"] == Decimal("1300.00")
    assert revenue_by_client[0]["unsent_revenue"] == Decimal("1300.00")

    assert metrics["top_hardware_items"][0]["description"] == "Firewall Appliance"
    assert metrics["top_hardware_items"][0]["quantity"] == 2
    assert metrics["top_hardware_items"][0]["revenue"] == Decimal("1000.00")

    assert metrics["clients_missing_rates"] == []


def test_calculate_ticket_metrics_flags_missing_rates(db_session):
    time_ticket = create_entry(
        db_session,
        {
            "client_key": "client_c",
            "client": "Client C",
            "start_iso": "2024-02-01T09:00:00",
            "end_iso": "2024-02-01T10:00:00",
        },
    )
    update_ticket(db_session, time_ticket, {"sent": 1})

    metrics = calculate_ticket_metrics(
        db_session,
        client_table={"client_c": {"name": "Client C"}},
    )

    assert metrics["clients_missing_rates"] == ["Client C"]
    assert metrics["totals"]["revenue_time"] == Decimal("0.00")
