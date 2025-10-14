from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import settings
from .db.session import Base, engine
from .db.migrate import run_migrations

# Ensure models are registered with SQLAlchemy metadata before create_all.
from .models import hardware as _hardware  # noqa: F401
from .models import ticket as _ticket  # noqa: F401
from .models import inventory as _inventory  # noqa: F401

# ---------- App init ----------
app = FastAPI(title="Time Tracker")

# Static & templates
BASE_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=str(settings.STATIC_DIR)), name="static")
TEMPLATES = Jinja2Templates(directory=str(settings.TEMPLATES_DIR))

# ---------- Jinja filters (restored) ----------
LOCAL_TZ = ZoneInfo(settings.TZ) if settings.TZ else None

def _to_dt(value: Any) -> datetime | None:
    """Best-effort conversion of strings/naive datetimes into aware datetimes in local TZ."""
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str) and value:
        # Try fromisoformat first; fall back to lenient parse if you add it later
        try:
            dt = datetime.fromisoformat(value)
        except Exception:
            return None
    else:
        return None

    if dt.tzinfo is None and LOCAL_TZ:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    if LOCAL_TZ:
        dt = dt.astimezone(LOCAL_TZ)
    return dt

def fmt_dt(value: Any, fmt: str = "%Y-%m-%d %I:%M %p") -> str:
    """Format a datetime-ish value (ISO string or datetime) for display."""
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""

def fmt_date(value: Any, fmt: str = "%Y-%m-%d") -> str:
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""

def fmt_time(value: Any, fmt: str = "%I:%M %p") -> str:
    dt = _to_dt(value)
    return dt.strftime(fmt) if dt else ""

# Register filters
TEMPLATES.env.filters["fmt_dt"] = fmt_dt
TEMPLATES.env.filters["fmt_date"] = fmt_date
TEMPLATES.env.filters["fmt_time"] = fmt_time

# ---------- DB init/migrations (unchanged) ----------
Base.metadata.create_all(bind=engine)
run_migrations(engine)

# ---------- Session middleware (UI login persistence) ----------
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.APP_SECRET,
    session_cookie=settings.SESSION_COOKIE_NAME,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",
    https_only=False,  # set True once the app is always accessed via HTTPS at the edge
)

# ---------- Routers ----------
# UI login routes (no session required)
from .routers import auth_ui as auth_ui_router  # type: ignore
app.include_router(auth_ui_router.router)

# UI pages/actions (session required via router dependency)
from .routers import ui as ui_router  # type: ignore
app.include_router(ui_router.router)

# APIs (headless; X-API-Key required via dependency inside each API router)
from .routers import api_tickets as api_tickets_router  # type: ignore
app.include_router(api_tickets_router.router, prefix="")

from .routers import clients as clients_router  # type: ignore
app.include_router(clients_router.router, prefix="")

from .routers import api_hardware as api_hardware_router  # type: ignore
app.include_router(api_hardware_router.router, prefix="")

from .routers import api_inventory as api_inventory_router  # type: ignore
app.include_router(api_inventory_router.router, prefix="")

from .routers import address as address_router  # type: ignore
app.include_router(address_router.router, prefix="")

# ---------- Exception handling ----------
# Redirect HTML 401s to /login while keeping JSON 401s for API/headless clients.
@app.exception_handler(StarletteHTTPException)
async def handle_http_exceptions(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 401:
        accept = (request.headers.get("accept") or "").lower()
        path = request.url.path
        is_html = "text/html" in accept
        is_api = path.startswith("/api")
        is_login = path.startswith("/login")
        if is_html and not is_api and not is_login:
            return RedirectResponse(url=f"/login?next={request.url}", status_code=302)
        return JSONResponse({"detail": exc.detail or "Unauthorized"}, status_code=401)
    return JSONResponse({"detail": exc.detail or "Error"}, status_code=exc.status_code)

__all__ = ["app"]
