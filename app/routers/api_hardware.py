from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..db.session import get_db
from ..schemas.hardware import HardwareCreate, HardwareUpdate, HardwareOut
from ..crud.hardware import list_hardware, get_hardware, create_hardware, update_hardware, delete_hardware
from ..deps.auth import require_ui_or_token

router = APIRouter(prefix="/api/v1/hardware", tags=["hardware"])


@router.get("", response_model=list[HardwareOut], dependencies=[Depends(require_ui_or_token)])
def api_list(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    return list_hardware(db, limit=limit, offset=offset)


@router.get("/{identifier}", response_model=HardwareOut, dependencies=[Depends(require_ui_or_token)])
def api_get(identifier: str, db: Session = Depends(get_db)):
    r = get_hardware(db, identifier)
    if not r:
        raise HTTPException(404, "Not found")
    return r


@router.post("", response_model=HardwareOut, dependencies=[Depends(require_ui_or_token)])
def api_create(payload: HardwareCreate, request: Request, db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_none=True)
    header_cost = _header_value(request, 'acquisition-cost', 'acquisition_cost', 'x-acquisition-cost', 'x_acquisition_cost')
    header_sale = _header_value(request, 'sales-price', 'sales_price', 'x-sales-price', 'x_sales_price')
    if header_cost and 'acquisition_cost' not in data:
        data['acquisition_cost'] = header_cost
    if header_sale and 'sales_price' not in data:
        data['sales_price'] = header_sale
    try:
        return create_hardware(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{item_id}", response_model=HardwareOut, dependencies=[Depends(require_ui_or_token)])
def api_update(item_id: int, payload: HardwareUpdate, request: Request, db: Session = Depends(get_db)):
    r = get_hardware(db, item_id)
    if not r:
        raise HTTPException(404, "Not found")
    data = payload.model_dump(exclude_none=True)
    header_cost = _header_value(request, 'acquisition-cost', 'acquisition_cost', 'x-acquisition-cost', 'x_acquisition_cost')
    header_sale = _header_value(request, 'sales-price', 'sales_price', 'x-sales-price', 'x_sales_price')
    if header_cost:
        data['acquisition_cost'] = header_cost
    if header_sale:
        data['sales_price'] = header_sale
    if not data:
        return r
    return update_hardware(db, r, data)


@router.delete("/{item_id}", dependencies=[Depends(require_ui_or_token)])
def api_delete(item_id: int, db: Session = Depends(get_db)):
    r = get_hardware(db, item_id)
    if not r:
        raise HTTPException(404, "Not found")
    delete_hardware(db, r)
    return {"status": "deleted"}

def _header_value(request: Request, *names: str) -> str | None:
    for name in names:
        value = request.headers.get(name)
        if value:
            value = value.strip()
            if value:
                return value
    return None

