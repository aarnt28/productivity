from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models.ticket import Ticket
from ..services.clientsync import load_client_table

TWOPLACES = Decimal("0.01")
HOUR_PLACES = Decimal("0.01")
SIXTY = Decimal(60)


def _to_decimal(value: Any) -> Decimal:
    """Best-effort conversion of incoming values to Decimal for currency math."""

    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return Decimal("0")
        cleaned = cleaned.replace("$", "").replace(",", "")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")
    return Decimal("0")


def _quantize_currency(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP) if value else Decimal("0.00")


def _quantize_hours(minutes: Decimal) -> Decimal:
    if not minutes:
        return Decimal("0")
    hours = minutes / SIXTY
    return hours.quantize(HOUR_PLACES, rounding=ROUND_HALF_UP)


def _ensure_client_name(ticket: Ticket, client_table: Dict[str, Any]) -> str:
    if ticket.client and ticket.client.strip():
        return ticket.client.strip()
    entry = client_table.get(ticket.client_key or "") if client_table else None
    if isinstance(entry, dict):
        name = entry.get("name") or entry.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    if ticket.client_key:
        return ticket.client_key
    return "Unknown"


def calculate_ticket_metrics(
    db: Session, client_table: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Aggregate reporting metrics for ticket revenue and activity."""

    tickets: Iterable[Ticket] = db.execute(select(Ticket)).scalars().all()
    table = client_table or load_client_table()

    totals = {
        "tickets_total": 0,
        "tickets_open": 0,
        "tickets_completed": 0,
        "tickets_sent": 0,
        "time_ticket_count": 0,
        "hardware_ticket_count": 0,
    }

    total_time_revenue = Decimal("0")
    total_hardware_revenue = Decimal("0")
    billable_minutes_total = Decimal("0")
    hardware_units_total = 0
    unsent_revenue_total = Decimal("0")
    unsent_time_revenue = Decimal("0")
    unsent_hardware_revenue = Decimal("0")
    unsent_ticket_count = 0

    client_metrics: Dict[str, Dict[str, Any]] = {}
    hardware_items: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"description": "", "quantity": 0, "revenue": Decimal("0")}
    )
    clients_missing_rates: set[str] = set()

    for ticket in tickets:
        totals["tickets_total"] += 1
        if ticket.completed:
            totals["tickets_completed"] += 1
        else:
            totals["tickets_open"] += 1
        if ticket.sent:
            totals["tickets_sent"] += 1
        else:
            unsent_ticket_count += 1

        client_name = _ensure_client_name(ticket, table)
        metrics = client_metrics.setdefault(
            client_name,
            {
                "client": client_name,
                "total": 0,
                "time_count": 0,
                "hardware_count": 0,
                "open_count": 0,
                "completed_count": 0,
                "time_revenue": Decimal("0"),
                "hardware_revenue": Decimal("0"),
                "billable_minutes": Decimal("0"),
                "unsent_revenue": Decimal("0"),
            },
        )

        metrics["total"] += 1
        if ticket.completed:
            metrics["completed_count"] += 1
        else:
            metrics["open_count"] += 1

        client_entry = table.get(ticket.client_key or "") if table else None
        support_rate = _to_decimal(client_entry.get("support_rate")) if isinstance(client_entry, dict) else Decimal("0")

        if (ticket.entry_type or "time").lower() == "hardware":
            totals["hardware_ticket_count"] += 1
            metrics["hardware_count"] += 1

            quantity = ticket.hardware_quantity or 1
            unit_price = _to_decimal(ticket.hardware_sales_price)
            revenue = unit_price * Decimal(quantity)
            total_hardware_revenue += revenue
            metrics["hardware_revenue"] += revenue
            hardware_units_total += quantity

            description = (ticket.hardware_description or "").strip() or "Hardware item"
            item = hardware_items[description]
            item["description"] = description
            item["quantity"] += quantity
            item["revenue"] += revenue

            if not ticket.sent:
                unsent_hardware_revenue += revenue
                metrics["unsent_revenue"] += revenue
        else:
            totals["time_ticket_count"] += 1
            metrics["time_count"] += 1

            minutes_value = ticket.rounded_minutes or ticket.minutes or ticket.elapsed_minutes or 0
            minutes_decimal = Decimal(int(minutes_value)) if minutes_value else Decimal("0")
            billable_minutes_total += minutes_decimal
            metrics["billable_minutes"] += minutes_decimal

            hours = minutes_decimal / SIXTY if minutes_decimal else Decimal("0")
            revenue = hours * support_rate
            total_time_revenue += revenue
            metrics["time_revenue"] += revenue

            if not support_rate:
                clients_missing_rates.add(client_name)

            if not ticket.sent:
                unsent_time_revenue += revenue
                metrics["unsent_revenue"] += revenue

        if not ticket.sent:
            unsent_revenue_total += revenue

    revenue_total = total_time_revenue + total_hardware_revenue

    tickets_by_client = []
    revenue_by_client = []
    for data in client_metrics.values():
        time_rev = _quantize_currency(data["time_revenue"])
        hardware_rev = _quantize_currency(data["hardware_revenue"])
        total_rev = _quantize_currency(time_rev + hardware_rev)
        billable_hours = _quantize_hours(data["billable_minutes"])
        unsent_rev = _quantize_currency(data["unsent_revenue"])

        tickets_by_client.append(
            {
                "client": data["client"],
                "total": data["total"],
                "time": data["time_count"],
                "hardware": data["hardware_count"],
                "open": data["open_count"],
                "completed": data["completed_count"],
            }
        )
        revenue_by_client.append(
            {
                "client": data["client"],
                "time_revenue": time_rev,
                "hardware_revenue": hardware_rev,
                "total_revenue": total_rev,
                "billable_hours": billable_hours,
                "unsent_revenue": unsent_rev,
            }
        )

    tickets_by_client.sort(key=lambda row: row["total"], reverse=True)
    revenue_by_client.sort(key=lambda row: row["total_revenue"], reverse=True)

    hardware_rows = [
        {
            "description": item["description"],
            "quantity": item["quantity"],
            "revenue": _quantize_currency(item["revenue"]),
        }
        for item in hardware_items.values()
    ]
    hardware_rows.sort(key=lambda row: row["revenue"], reverse=True)

    totals.update(
        {
            "hardware_units_sold": hardware_units_total,
            "billable_hours": float(_quantize_hours(billable_minutes_total)),
            "billable_minutes": int(billable_minutes_total),
            "revenue_time": _quantize_currency(total_time_revenue),
            "revenue_hardware": _quantize_currency(total_hardware_revenue),
            "revenue_total": _quantize_currency(revenue_total),
            "average_revenue_per_ticket": _quantize_currency(
                revenue_total / totals["tickets_total"]
            )
            if totals["tickets_total"]
            else Decimal("0.00"),
            "average_hours_per_time_ticket": float(
                _quantize_hours(
                    billable_minutes_total / totals["time_ticket_count"]
                    if totals["time_ticket_count"]
                    else Decimal("0")
                )
            ),
            "unsent_revenue": _quantize_currency(unsent_revenue_total),
            "unsent_time_revenue": _quantize_currency(unsent_time_revenue),
            "unsent_hardware_revenue": _quantize_currency(unsent_hardware_revenue),
            "unsent_ticket_count": unsent_ticket_count,
            "clients_with_activity": len(client_metrics),
        }
    )

    return {
        "totals": totals,
        "tickets_by_client": tickets_by_client,
        "revenue_by_client": revenue_by_client,
        "top_hardware_items": hardware_rows[:10],
        "clients_missing_rates": sorted(clients_missing_rates),
    }


__all__ = ["calculate_ticket_metrics"]

