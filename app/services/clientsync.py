from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any
from ..core.config import settings


def _seed_paths():
    # Prefer /data/client_table.json, fall back to repo app/client_table.json
    data_json = settings.DATA_DIR / "client_table.json"
    repo_json = settings.BASE_DIR / "app" / "client_table.json"
    return data_json, repo_json


def _normalize_table(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Return table keyed by client_key. Converts legacy name-keyed data."""
    if not raw:
        return {}

    needs_migration = False
    for display_name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        legacy_key = payload.get("key")
        if legacy_key and legacy_key != display_name:
            needs_migration = True
            break

    if not needs_migration:
        # Ensure every entry has a name field; if not, inject from key
        for key, entry in raw.items():
            if isinstance(entry, dict) and "name" not in entry:
                entry["name"] = entry.get("display_name", key)
        return raw

    migrated: Dict[str, Any] = {}
    for display_name, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        legacy_key = payload.get("key")
        if not legacy_key:
            continue
        entry = dict(payload)
        entry.pop("key", None)
        entry.setdefault("name", display_name)
        migrated[legacy_key] = entry
    return migrated


def load_client_table() -> Dict[str, Any]:
    data_json, repo_json = _seed_paths()
    src = data_json if data_json.exists() else repo_json
    if src.exists():
        raw = json.loads(src.read_text(encoding="utf-8"))
    else:
        raw = {}
    normalized = _normalize_table(raw)
    # If normalization changed structure and we were reading from writable location, persist upgrade
    if normalized != raw:
        save_client_table(normalized)
    return normalized


def save_client_table(payload: Dict[str, Any]) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    dst = settings.DATA_DIR / "client_table.json"
    # Ensure each entry has a name and strip empty dicts
    cleaned: Dict[str, Any] = {}
    for key, entry in (payload or {}).items():
        if not isinstance(entry, dict):
            continue
        entry = dict(entry)
        entry.setdefault("name", key)
        cleaned[key] = entry
    dst.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")


def get_client_entry(client_key: str) -> Dict[str, Any] | None:
    table = load_client_table()
    return table.get(client_key)


def resolve_client_name(client_key: str) -> str | None:
    entry = get_client_entry(client_key)
    if not entry:
        return None
    return entry.get("name") or entry.get("display_name") or client_key


def resolve_client_key(client_name: str) -> str | None:
    """Return the client_key for a given display/client name."""
    if not client_name:
        return None

    sought = client_name.strip().casefold()
    if not sought:
        return None

    table = load_client_table()
    for key, entry in table.items():
        if not isinstance(entry, dict):
            continue

        name = (entry.get("name") or "").strip()
        display_name = (entry.get("display_name") or "").strip()

        if name and name.casefold() == sought:
            return key
        if display_name and display_name.casefold() == sought:
            return key

        # Allow lookups where the caller already provided the client_key
        if key.casefold() == sought:
            return key

    return None
