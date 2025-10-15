from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.catalog import CatalogItem, UnitEnum
from app.schemas.catalog import (
    AliasCreate,
    AliasOut,
    CatalogItemCreate,
    CatalogItemOut,
    CatalogItemSummary,
    ResolveResult,
)
from app.services.barcode import ensure_alias, resolve_catalog_item


router = APIRouter(prefix="/api/v2/catalog", tags=["catalog"], dependencies=[Depends(api_auth)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/items", response_model=List[CatalogItemSummary])
def list_catalog_items(
    query: Optional[str] = Query(default=None, description="Search by SKU or name"),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(CatalogItem)
    if query:
        pattern = f"%{query.lower()}%"
        stmt = stmt.where(
            func.lower(CatalogItem.sku).like(pattern) | func.lower(CatalogItem.name).like(pattern)
        )
    stmt = stmt.order_by(CatalogItem.name.asc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return rows


@router.post("/items", response_model=CatalogItemOut, status_code=status.HTTP_201_CREATED)
def create_or_update_item(payload: CatalogItemCreate, db: Session = Depends(get_db)):
    existing = db.scalar(select(CatalogItem).where(CatalogItem.sku == payload.sku))
    if existing:
        for field, value in payload.model_dump().items():
            if value is not None:
                setattr(existing, field, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    item = CatalogItem(
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        unit=UnitEnum(payload.unit),
        default_sell_price=payload.default_sell_price,
        default_cost=payload.default_cost,
        tax_category=payload.tax_category,
        is_active=payload.is_active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/aliases", response_model=AliasOut, status_code=status.HTTP_201_CREATED)
def add_alias(payload: AliasCreate, db: Session = Depends(get_db)):
    if not db.get(CatalogItem, payload.catalog_item_id):
        raise HTTPException(status_code=404, detail="Catalog item not found")
    alias = ensure_alias(
        db,
        catalog_item_id=payload.catalog_item_id,
        alias_value=payload.alias,
        kind=payload.kind,
    )
    return alias


@router.get("/resolve/{alias}", response_model=ResolveResult)
def resolve_alias(alias: str, db: Session = Depends(get_db)):
    resolved = resolve_catalog_item(db, alias)
    if not resolved:
        raise HTTPException(status_code=404, detail="Code not found")
    item = resolved.catalog_item
    return ResolveResult(catalog_item_id=item.id, sku=item.sku, name=item.name)

