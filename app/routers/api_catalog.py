from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.sku_alias import SkuAlias
from app.models.hardware import Hardware
from app.schemas.catalog import AliasCreate, AliasOut, ResolveResult
from app.services.barcode import resolve_any_code

router = APIRouter(prefix="/api/v1/catalog", tags=["catalog"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/resolve/{code}", response_model=ResolveResult, dependencies=[Depends(api_auth)])
def resolve_code(code: str, db: Session = Depends(get_db)):
    found = resolve_any_code(db, code)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found")
    hw, _ = found
    return ResolveResult(hardware_id=hw.id, barcode=hw.barcode, description=hw.description)

@router.post("/aliases", response_model=AliasOut, status_code=201, dependencies=[Depends(api_auth)])
def add_alias(payload: AliasCreate, db: Session = Depends(get_db)):
    if not db.get(Hardware, payload.hardware_id):
        raise HTTPException(status_code=404, detail="Hardware not found")
    exists = db.scalar(select(SkuAlias).where(SkuAlias.alias == payload.alias))
    if exists:
        raise HTTPException(status_code=409, detail="Alias already exists")

    alias = SkuAlias(
        hardware_id=payload.hardware_id,
        alias=payload.alias.strip(),
        kind=payload.kind.strip() if payload.kind else "UPC",
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias

@router.get("/aliases", response_model=list[AliasOut], dependencies=[Depends(api_auth)])
def list_aliases(db: Session = Depends(get_db)):
    rows = db.scalars(select(SkuAlias).order_by(SkuAlias.id.desc())).all()
    return list(rows)
