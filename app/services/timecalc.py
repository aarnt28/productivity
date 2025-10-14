from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

def parse_iso(ts: str, tz: str) -> datetime | None:
    """Parse an ISO-8601 timestamp string.
    If naive, attach the provided tz. Returns None if ts is falsy.
    """
    if not ts:
        return None
    dt = datetime.fromisoformat(ts.replace('Z','+00:00'))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(tz))
    return dt

def compute_minutes(start_iso: str | None, end_iso: str | None, tz: str) -> int:
    """Return whole minutes between start and end (non-negative)."""
    s = parse_iso(start_iso, tz)
    e = parse_iso(end_iso, tz)
    if not s or not e:
        return 0
    delta = int((e - s).total_seconds() // 60)
    return max(delta, 0)

def round_minutes(mins: int, quantum: int = 15) -> tuple[int, int, str]:
    """
    Business rule:
      - anything under 5 mins rounds down to 0
      - otherwise always round UP to the next 15-minute increment
    Returns: (elapsed_minutes, rounded_minutes, rounded_hours_str)
    """
    if mins < 0:
        mins = 0
    if mins < 5:
        rmin = 0
    else:
        rmin = ((mins + quantum - 1) // quantum) * quantum
    rhours = f"{rmin/60:.2f}"
    return mins, rmin, rhours
