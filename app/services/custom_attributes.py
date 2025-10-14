from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List, Set

from ..core.config import settings

# Keys that are considered demographic/built-in and should not be treated as custom attributes.
DEMOGRAPHIC_ATTRIBUTE_KEYS: Set[str] = {
    "address_line1",
    "address_line2",
    "city",
    "state",
    "postal_code",
    "support_hours_allowance",
    "primary_contact_name",
    "primary_contact_phone",
    "primary_contact_email",
    "office_manager_name",
    "office_manager_phone",
    "office_manager_email",
}

# Other reserved keys that belong to client metadata and must not be managed as custom attributes.
RESERVED_CLIENT_KEYS: Set[str] = {"name", "display_name", "key"} | DEMOGRAPHIC_ATTRIBUTE_KEYS


def _file_path() -> Path:
    return settings.DATA_DIR / "custom_attributes.json"


def _discover_from_clients() -> Set[str]:
    try:
        from .clientsync import load_client_table  # Local import to avoid circular dependency
    except ImportError:  # pragma: no cover - defensive fallback
        return set()

    table = load_client_table()
    discovered: Set[str] = set()
    for entry in table.values():
        if not isinstance(entry, dict):
            continue
        for key in entry.keys():
            if key not in RESERVED_CLIENT_KEYS:
                discovered.add(str(key))
    return discovered


def _normalize_keys(raw: Iterable[str]) -> List[str]:
    normalized: Set[str] = set()
    for key in raw:
        if not isinstance(key, str):
            continue
        cleaned = key.strip()
        if not cleaned or cleaned in RESERVED_CLIENT_KEYS:
            continue
        normalized.add(cleaned)
    return sorted(normalized)


def load_custom_attribute_keys() -> List[str]:
    path = _file_path()
    keys: List[str] = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                keys = _normalize_keys(data)
        except json.JSONDecodeError:
            keys = []
    if not keys:
        keys = _normalize_keys(_discover_from_clients())
        save_custom_attribute_keys(keys)
    return keys


def save_custom_attribute_keys(keys: Iterable[str]) -> List[str]:
    normalized = _normalize_keys(keys)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _file_path()
    path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False), encoding="utf-8")
    return normalized


def add_custom_attribute_key(key: str) -> List[str]:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ValueError("Attribute key cannot be blank")
    if cleaned in RESERVED_CLIENT_KEYS:
        raise ValueError("Attribute key is reserved")
    keys = load_custom_attribute_keys()
    if cleaned in keys:
        raise KeyError("Attribute key already exists")
    keys.append(cleaned)
    return save_custom_attribute_keys(keys)


def remove_custom_attribute_key(key: str) -> List[str]:
    cleaned = (key or "").strip()
    if not cleaned:
        raise ValueError("Attribute key cannot be blank")
    keys = load_custom_attribute_keys()
    if cleaned not in keys:
        raise KeyError("Attribute key not found")
    filtered = [k for k in keys if k != cleaned]
    return save_custom_attribute_keys(filtered)
