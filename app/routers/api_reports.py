from __future__ import annotations
from datetime import datetime, date, time, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.session import SessionLocal
from app.deps.auth import api_auth

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _utc_bounds(d: date) -> tuple[datetime, datetime]:
    # Store UTC in DB if possible; if local, this still yields a consistent day slice.
    start = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
    end   = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)
    return start, end

@router.get("/daily-rollup", dependencies=[Depends(api_auth)])
def daily_rollup(date_str: str = Query(default=None), db: Session = Depends(get_db)):
    """
    Draft 'money made' = SUM(tickets.calculated_value) for time/hardware entries that day.
    'Money spent' (COGS) = SUM(ABS(inventory_events.change) * unit_cost) for negative changes that day.
    """
    if date_str:
        d = (datetime.fromisoformat(date_str).date()
             if "T" not in date_str else datetime.fromisoformat(date_str).date())
    else:
        d = datetime.utcnow().date()
    start, end = _utc_bounds(d)

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
