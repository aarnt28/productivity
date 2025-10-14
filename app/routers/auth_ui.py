from __future__ import annotations
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from ..core.config import settings
from ..core.jinja import get_templates  # <<< use centralized templates with filters

try:
    import bcrypt  # type: ignore
except Exception:
    bcrypt = None

router = APIRouter()
templates = get_templates()

@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/"):
    if request.session.get("ui_authenticated"):
        return RedirectResponse(url=next, status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "next": next, "error": ""})

def _verify_password(plain: str) -> bool:
    hp = (settings.UI_PASSWORD_HASH or "").strip()
    if hp and bcrypt:
        try:
            return bcrypt.checkpw(plain.encode("utf-8"), hp.encode("utf-8"))
        except Exception:
            return False
    return plain == (settings.UI_PASSWORD or "")

@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    remember: str = Form(""),
    next: str = Form("/"),
):
    if username != (settings.UI_USERNAME or "") or not _verify_password(password):
        return templates.TemplateResponse(
            "login.html", {"request": request, "next": next, "error": "Invalid username or password"}, status_code=401
        )
    request.session["ui_authenticated"] = True
    return RedirectResponse(url=next or "/", status_code=302)

@router.get("/logout")
def logout(request: Request, next: str = "/"):
    request.session.clear()
    return RedirectResponse(url=next or "/", status_code=302)
