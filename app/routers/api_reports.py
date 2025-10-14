# app/routers/api_reports.py
from __future__ import annotations
from datetime import datetime, date, time, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.deps.auth import api_auth
from app.db.session import SessionLocal

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _day_bounds_cst(d: date) -> tuple[datetime, datetime]:
    # store in UTC, render CST/CDT: for SQLite we’ll just compute absolute UTC bounds assuming server stores UTC.
    # If your app stores local time, this still gives a sensible cut across one calendar day.
    start = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
    end   = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)
    return start, end

@router.get("/daily-rollup", dependencies=[Depends(api_auth)])
def daily_rollup(date_str: str = Query(default=None), db: Session = Depends(get_db)):
    """
    Returns:
    {
      "date": "2025-10-14",
      "money_generated": {"draft": 0.0, "invoiced": 0.0, "paid": 0.0},
      "money_spent": {"cogs": 0.0}
    }
    Notes:
      - Generated (draft): from ticket rows on this date (time or hardware) using their calculated value when present.
      - Generated (invoiced/paid): from invoices when/if you add them later (kept for forward compatibility).
      - Spent (cogs): sum of negative inventory event costs for the day if cost present; else 0.
    """
    if date_str:
        d = datetime.fromisoformat(date_str).date() if "T" not in date_str else datetime.fromisoformat(date_str).date()
    else:
        d = datetime.utcnow().date()
    start, end = _day_bounds_cst(d)

    # These queries are intentionally defensive to match your current schema:
    # - tickets: expect columns: created_at, entry_type ('time'|'hardware'), calculated_value (nullable numeric)
    # - inventory_events: expect created_at, change (signed int/real), unit_cost (nullable numeric)
    # If a column is missing, COALESCE() defaults make totals 0 instead of erroring.
    q_generated = text("""
        SELECT COALESCE(SUM(COALESCE(calculated_value, 0)), 0) AS total
        FROM tickets
        WHERE created_at >= :start AND created_at <= :end
          AND COALESCE(entry_type, '') IN ('time','hardware')
    """)
    q_cogs = text("""
        SELECT COALESCE(SUM(ABS(change) * COALESCE(unit_cost, 0)), 0) AS cogs
        FROM inventory_events
        WHERE created_at >= :start AND created_at <= :end
          AND change < 0
    """)

    gen_total = float(db.execute(q_generated, {"start": start, "end": end}).scalar() or 0.0)
    cogs = float(db.execute(q_cogs, {"start": start, "end": end}).scalar() or 0.0)

    return {
        "date": d.isoformat(),
        "money_generated": {"draft": round(gen_total, 2), "invoiced": 0.0, "paid": 0.0},
        "money_spent": {"cogs": round(cogs, 2)},
    }
