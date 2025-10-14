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
from app.crud.hardware import create_hardware, get_hardware, list_hardware
from app.crud.inventory import (
    record_inventory_event,
    list_inventory_events,
    delete_event,
)
from app.routers.api_inventory import _lookup_hardware
from app.models.hardware import Hardware
from app.crud.tickets import create_entry

# Ensure models are imported so metadata is populated
from app.models import hardware as hardware_model  # noqa: F401
from app.models import inventory as inventory_model  # noqa: F401


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


def test_record_inventory_event_tracks_costs(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "ABC123", "description": "Widget"},
    )

    event = record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=4,
        source="ui:receive",
        note="Initial stock",
        counterparty_name="Vendor A",
        counterparty_type="vendor",
        actual_cost=100.0,
    )

    assert event.counterparty_name == "Vendor A"
    assert event.counterparty_type == "vendor"
    assert event.actual_cost == pytest.approx(100.0)
    assert event.unit_cost == pytest.approx(25.0)

    sale_event = record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=-2,
        source="ui:use",
        note="Sold to client",
        counterparty_name="Client A",
        counterparty_type="client",
        actual_cost=40.0,
        sale_price=90.0,
    )

    assert sale_event.sale_price_total == pytest.approx(90.0)
    assert sale_event.sale_unit_price == pytest.approx(45.0)
    assert sale_event.actual_cost == pytest.approx(40.0)
    assert sale_event.unit_cost == pytest.approx(20.0)
    assert sale_event.profit_total == pytest.approx(50.0)
    assert sale_event.profit_unit == pytest.approx(25.0)


def test_hardware_common_vendors_and_average_cost(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "XYZ789", "description": "Gadget"},
    )

    record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=4,
        source="ui:receive",
        note="Vendor A shipment",
        counterparty_name="Vendor A",
        counterparty_type="vendor",
        actual_cost=100.0,
    )
    record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=2,
        source="ui:receive",
        note="Vendor B shipment",
        counterparty_name="Vendor B",
        counterparty_type="vendor",
        actual_cost=60.0,
    )
    record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=-2,
        source="ui:use",
        note="Used by client",
        counterparty_name="Client A",
        counterparty_type="client",
    )

    rows = list_hardware(db_session, limit=10)
    assert rows
    gadget = next(row for row in rows if row.id == hardware.id)
    assert gadget.common_vendors == ["Vendor A", "Vendor B"]
    assert gadget.average_unit_cost == pytest.approx((25.0 + 30.0) / 2)


def test_create_entry_records_sale_totals(db_session):
    hardware = create_hardware(
        db_session,
        {
            "barcode": "SALE123",
            "description": "Bundle",
            "acquisition_cost": "45.00",
        },
    )

    create_entry(
        db_session,
        {
            "client_key": "client-1",
            "client": "Client 1",
            "start_iso": "2023-01-01T00:00:00Z",
            "end_iso": "2023-01-01T01:00:00Z",
            "entry_type": "hardware",
            "hardware_id": hardware.id,
            "hardware_quantity": 2,
            "hardware_sales_price": "150",
            "note": "Sold bundle",
        },
    )

    events = list_inventory_events(db_session)
    sale_event = next(e for e in events if e.source == "ticket")

    assert sale_event.change == -2
    assert sale_event.sale_price_total == pytest.approx(300.0)
    assert sale_event.actual_cost == pytest.approx(90.0)
    assert sale_event.profit_total == pytest.approx(210.0)


def test_delete_inventory_event(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "DEL123", "description": "Disposable"},
    )
    event = record_inventory_event(
        db_session,
        hardware_id=hardware.id,
        change=1,
        source="ui:receive",
        counterparty_name="Vendor D",
        counterparty_type="vendor",
        actual_cost=10.0,
    )

    events_before = list_inventory_events(db_session)
    assert any(e.id == event.id for e in events_before)

    delete_event(db_session, event)

    events_after = list_inventory_events(db_session)
    assert all(e.id != event.id for e in events_after)


def test_create_hardware_normalizes_numeric_barcodes(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": " 123456789012 ", "description": "Legacy"},
    )

    assert hardware.barcode == "0123456789012"


def test_lookup_accepts_missing_leading_zero(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "0123456789012", "description": "Scanner"},
    )

    match = _lookup_hardware(db_session, None, "123456789012")
    assert match.id == hardware.id


def test_get_hardware_by_barcode(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "ABC123", "description": "Barcode fetch"},
    )

    fetched = get_hardware(db_session, "ABC123")
    assert fetched is not None
    assert fetched.id == hardware.id


def test_get_hardware_accepts_barcode_aliases(db_session):
    hardware = create_hardware(
        db_session,
        {"barcode": "0123456789012", "description": "Aliased barcode"},
    )

    fetched = get_hardware(db_session, "123456789012")
    assert fetched is not None
    assert fetched.id == hardware.id


def test_list_hardware_backfills_legacy_barcodes(db_session):
    legacy = Hardware(
        barcode="123456789012",
        description="Legacy barcode",
        acquisition_cost=None,
        sales_price=None,
        created_at="2023-01-01T00:00:00Z",
    )
    db_session.add(legacy)
    db_session.commit()

    rows = list_hardware(db_session)
    updated = next(row for row in rows if row.id == legacy.id)
    assert updated.barcode == "0123456789012"
