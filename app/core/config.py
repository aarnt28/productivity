from __future__ import annotations
import os
from pathlib import Path

class Settings:
    BASE_DIR = Path(__file__).resolve().parents[2]
    DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
    TEMPLATES_DIR = BASE_DIR / "app" / "templates"
    STATIC_DIR = BASE_DIR / "app" / "static"
    TZ = os.getenv("TZ", "America/Chicago")

    # ---- API (headless) authentication
    API_TOKEN = os.getenv("API_TOKEN", "")  # X-API-Key must match this (if set)

    # ---- UI (browser) authentication
    # Cookie/session secret. MUST be long & random in production.
    APP_SECRET = os.getenv("APP_SECRET", "dev-insecure-secret-change-me")
    # Simple single-user creds for the UI (browser) login
    UI_USERNAME = os.getenv("UI_USERNAME", "admin")
    # Store a bcrypt hash if you have one; otherwise fallback to plain.
    # If UI_PASSWORD_HASH is set, it takes precedence over UI_PASSWORD.
    UI_PASSWORD = os.getenv("UI_PASSWORD", "change-me")
    UI_PASSWORD_HASH = os.getenv("UI_PASSWORD_HASH", "")  # e.g. $2b$12$...

    # Cookie settings
    SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "tt_session")
    SESSION_MAX_AGE = int(os.getenv("SESSION_MAX_AGE", "2592000"))  # 30 days in seconds

    DB_URL = os.getenv("DB_URL", f"sqlite:///{DATA_DIR}/data.db")

    # App binding (container listens on 0.0.0.0:8089; host/Windows maps via compose)
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8089"))

    # Address autocomplete & geocoding (Geoapify)
    GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "")
    GEOAPIFY_AUTOCOMPLETE_URL = os.getenv(
        "GEOAPIFY_AUTOCOMPLETE_URL",
        "https://api.geoapify.com/v1/geocode/autocomplete",
    )
    GEOAPIFY_GEOCODE_URL = os.getenv(
        "GEOAPIFY_GEOCODE_URL",
        "https://api.geoapify.com/v1/geocode/search",
    )
    GEOAPIFY_PLACE_URL = os.getenv(
        "GEOAPIFY_PLACE_URL",
        "https://api.geoapify.com/v1/geocode/retrieve",
    )

settings = Settings()
