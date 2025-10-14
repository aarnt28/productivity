from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from ..services.clientsync import (
    load_client_table,
    save_client_table,
    get_client_entry,
    resolve_client_key,
)
from ..services.custom_attributes import (
    add_custom_attribute_key,
    load_custom_attribute_keys,
    remove_custom_attribute_key,
)
from ..deps.auth import require_ui_or_token

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])

# ---- Public READ endpoints (no token) ----
@router.get("")
def list_clients():
    return {
        "clients": load_client_table(),
        "attribute_keys": load_custom_attribute_keys(),
    }


@router.get("/attributes")
def list_custom_attributes():
    return {"attribute_keys": load_custom_attribute_keys()}

@router.get("/lookup")
def get_client_by_name(name: str = Query(..., min_length=1, description="Client display name")):
    client_key = resolve_client_key(name)
    if not client_key:
        raise HTTPException(404, "Not found")
    entry = get_client_entry(client_key)
    if not entry:
        raise HTTPException(404, "Not found")
    return {"client_key": client_key, "client": entry}

@router.get("/{client_key}")
def get_client(client_key: str):
    entry = get_client_entry(client_key)
    if not entry:
        raise HTTPException(404, "Not found")
    return {"client_key": client_key, "client": entry}

# ---- Write endpoints (UI allowed; headless needs token) ----
@router.post("", dependencies=[Depends(require_ui_or_token)])
def create_client(payload: Dict[str, Any]):
    client_key = (payload.get("client_key") or "").strip()
    name = (payload.get("name") or "").strip()
    if not client_key:
        raise HTTPException(422, "Missing 'client_key'")
    if not name:
        raise HTTPException(422, "Missing 'name'")

    table = load_client_table()
    if client_key in table:
        raise HTTPException(409, "Client already exists")

    attributes = payload.get("attributes") or {}
    entry = dict(attributes)
    entry["name"] = name
    table[client_key] = entry
    save_client_table(table)
    return {"status": "created", "client_key": client_key, "client": entry}

@router.patch("/{client_key}", dependencies=[Depends(require_ui_or_token)])
def update_client(client_key: str, payload: Dict[str, Any]):
    table = load_client_table()
    if client_key not in table:
        raise HTTPException(404, "Not found")
    entry = dict(table[client_key])

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise HTTPException(422, "'name' cannot be blank")
        entry["name"] = name

    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        entry.update(attributes)

    table[client_key] = entry
    save_client_table(table)
    return {"status": "updated", "client_key": client_key, "client": entry}

@router.post("/{client_key}/delete", dependencies=[Depends(require_ui_or_token)])
@router.delete("/{client_key}", dependencies=[Depends(require_ui_or_token)])
def delete_client(client_key: str):
    table = load_client_table()
    if client_key not in table:
        raise HTTPException(404, "Not found")
    table.pop(client_key, None)
    save_client_table(table)
    return {"status": "deleted", "client_key": client_key}


@router.post("/attributes", dependencies=[Depends(require_ui_or_token)])
def create_custom_attribute(payload: Dict[str, Any]):
    key = (payload.get("key") or "").strip()
    if not key:
        raise HTTPException(422, "Missing 'key'")
    try:
        keys = add_custom_attribute_key(key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"status": "created", "attribute_keys": keys}


@router.delete("/attributes/{attribute_key}", dependencies=[Depends(require_ui_or_token)])
def delete_custom_attribute(attribute_key: str):
    key = (attribute_key or "").strip()
    if not key:
        raise HTTPException(422, "Invalid attribute key")
    try:
        keys = remove_custom_attribute_key(key)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    table = load_client_table()
    changed = False
    for client_key, entry in list(table.items()):
        if not isinstance(entry, dict):
            continue
        if key in entry:
            entry.pop(key, None)
            table[client_key] = entry
            changed = True
    if changed:
        save_client_table(table)

    return {"status": "deleted", "attribute_keys": keys}
