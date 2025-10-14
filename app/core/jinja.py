from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from .config import settings

# We keep this module tiny and focused: build a templates environment and register filters.

_LOCAL_TZ = ZoneInfo(settings.TZ) if settings.TZ else None

def _to_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            return None
    else:
        return None

    if dt.tzinfo is None and _LOCAL_TZ:
        dt = dt.replace(tzinfo=_LOCAL_TZ)
    if _LOCAL_TZ:
        dt = dt.astimezone(_LOCAL_TZ)
    return dt

def _fmt_dt(value: Any, fmt: str = "%Y-%m-%d %I:%M %p") -> str:
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""

def _fmt_dt_compact(value: Any) -> str:
    dt = _to_dt(value)
    if not dt:
        return ""
    return f"{dt.month}/{dt.day} {dt.strftime('%H:%M')}"

def _fmt_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""

def _fmt_time(value: Any, fmt: str = "%I:%M %p") -> str:
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""


def _fmt_currency(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return f"${number:,.2f}"

def get_templates() -> Jinja2Templates:
    """Create a Jinja2Templates instance with our standard filters registered."""
    templates = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))
    env = templates.env
    env.filters["fmt_dt"] = _fmt_dt
    env.filters["fmt_dt_compact"] = _fmt_dt_compact
    env.filters["fmt_date"] = _fmt_date
    env.filters["fmt_time"] = _fmt_time
    env.filters["fmt_currency"] = _fmt_currency
    return templates

