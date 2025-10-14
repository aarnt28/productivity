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

os.environ.setdefault("DATA_DIR", str(ROOT / "data"))  # ensure consistent paths for client table reads
os.environ.setdefault("TZ", "UTC")

from app.db.session import Base  # noqa: E402
from app.models.ticket import Ticket  # noqa: E402
from app.models.work import Client  # noqa: E402
from app.schemas.billing import (  # noqa: E402
    InvoiceCreateRequest,
    InvoiceLineCreate,
    InvoiceLineType,
    InvoiceSourceType,
)
from app.services.billing import create_invoice, get_unbilled  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def _make_ticket(*, entry_type: str, **kwargs) -> Ticket:
    defaults = {
        "client": "Client A",
        "client_key": "client_a",
        "start_iso": "2025-01-01T09:00:00",
        "end_iso": "2025-01-01T10:00:00",
        "elapsed_minutes": 60,
        "rounded_minutes": 60,
        "rounded_hours": "1.00",
        "note": "Work log",
        "completed": 1,
        "sent": 0,
        "invoice_number": None,
        "created_at": "2025-01-01T09:00:00Z",
        "minutes": 60,
        "invoiced_total": "120.00",
        "calculated_value": "120.00",
    }
    defaults.update(kwargs)
    ticket = Ticket(entry_type=entry_type, **defaults)
    return ticket


def test_get_unbilled_includes_legacy_tickets_and_create_invoice_marks_sent(db_session):
    client = Client(name="Client A")
    db_session.add(client)
    db_session.flush()

    time_ticket = _make_ticket(entry_type="time")
    hardware_ticket = _make_ticket(
        entry_type="hardware",
        end_iso="2025-01-02T09:30:00",
        elapsed_minutes=30,
        rounded_minutes=30,
        rounded_hours="0.50",
        created_at="2025-01-02T09:00:00Z",
        minutes=30,
        hardware_description="Edge Router",
        hardware_sales_price="75.00",
        hardware_quantity=1,
        invoiced_total="75.00",
        calculated_value="75.00",
    )
    db_session.add_all([time_ticket, hardware_ticket])
    db_session.commit()

    unbilled = get_unbilled(db_session, None)

    assert len(unbilled.time) == 1
    assert len(unbilled.parts) == 1

    time_item = unbilled.time[0]
    part_item = unbilled.parts[0]

    assert time_item.legacy is True
    assert part_item.legacy is True
    assert time_item.source_type == InvoiceSourceType.TIME_ENTRY.value
    assert part_item.source_type == InvoiceSourceType.PART_USAGE.value
    assert time_item.source_id < 0  # legacy tickets use negative source ids
    assert part_item.source_id < 0

    time_qty = Decimal(time_item.minutes) / Decimal(60) or Decimal("1")
    part_qty = Decimal(part_item.qty)

    payload = InvoiceCreateRequest(
        client_id=client.id,
        lines=[
            InvoiceLineCreate(
                line_type=InvoiceLineType.LABOR,
                description=time_item.description or "Time",
                qty=time_qty,
                unit_price=Decimal(time_item.resolved_bill_rate),
                source_type=InvoiceSourceType(time_item.source_type),
                source_id=time_item.source_id,
            ),
            InvoiceLineCreate(
                line_type=InvoiceLineType.PART,
                description=f"{part_item.name} ({part_item.sku})",
                qty=part_qty,
                unit_price=Decimal(part_item.resolved_sell_price),
                source_type=InvoiceSourceType(part_item.source_type),
                source_id=part_item.source_id,
            ),
        ],
        tax=Decimal("0"),
    )

    invoice = create_invoice(db_session, payload)
    db_session.commit()

    db_session.refresh(time_ticket)
    db_session.refresh(hardware_ticket)

    assert invoice.subtotal == Decimal("195.00")
    assert {line.source_id for line in invoice.lines} == {time_item.source_id, part_item.source_id}
    assert time_ticket.sent == 1
    assert hardware_ticket.sent == 1
    assert time_ticket.invoice_number == f"INV-{invoice.id}"
    assert hardware_ticket.invoice_number == f"INV-{invoice.id}"
