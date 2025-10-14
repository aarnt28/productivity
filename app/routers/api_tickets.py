from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..schemas.ticket import EntryCreate, EntryUpdate, EntryOut
from ..crud.tickets import list_tickets, list_active_tickets, get_ticket, create_entry, update_ticket, delete_ticket
from ..deps.auth import require_ui_or_token

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])

@router.get("/active", response_model=list[EntryOut], dependencies=[Depends(require_ui_or_token)])
def api_list_active(client_key: str | None = Query(default=None), db: Session = Depends(get_db)):
    return list_active_tickets(db, client_key=client_key)


@router.get("", response_model=list[EntryOut], dependencies=[Depends(require_ui_or_token)])
def api_list(db: Session = Depends(get_db)):
    return list_tickets(db)


@router.get("/{entry_id}", response_model=EntryOut, dependencies=[Depends(require_ui_or_token)])
def api_get(entry_id: int, db: Session = Depends(get_db)):
    r = get_ticket(db, entry_id)
    if not r:
        raise HTTPException(404, "Not found")
    return r


@router.post("", response_model=EntryOut, status_code=201, dependencies=[Depends(require_ui_or_token)])
def api_create(payload: EntryCreate, db: Session = Depends(get_db)):
    try:
        return create_entry(db, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{entry_id}", response_model=EntryOut, dependencies=[Depends(require_ui_or_token)])
def api_update(entry_id: int, payload: EntryUpdate, db: Session = Depends(get_db)):
    r = get_ticket(db, entry_id)
    if not r:
        raise HTTPException(404, "Not found")
    try:
        data = {k: v for k, v in payload.model_dump().items() if v is not None}
        return update_ticket(db, r, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{entry_id}", dependencies=[Depends(require_ui_or_token)])
def api_delete(entry_id: int, db: Session = Depends(get_db)):
    r = get_ticket(db, entry_id)
    if not r:
        raise HTTPException(404, "Not found")
    delete_ticket(db, r)
    return {"status": "deleted"}
