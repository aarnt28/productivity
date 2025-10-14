from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.catalog import AliasKindEnum, CatalogItem, SkuAlias, UnitEnum


@dataclass(slots=True)
class BarcodeResolution:
    catalog_item: CatalogItem
    matched_on_alias: bool
    alias: Optional[SkuAlias]
    created: bool


def _normalize(code: str | None) -> str:
    return (code or "").strip()


def resolve_catalog_item(
    db: Session,
    code: str,
    *,
    auto_create: bool = True,
    created_by: str | None = None,
) -> Optional[BarcodeResolution]:
    """
    Resolve an arbitrary code (SKU, UPC/EAN, vendor code) to a catalog item.

    Resolution order:
    1. CatalogItem.sku (direct match)
    2. SkuAlias.alias
    3. If ``auto_create`` is True -> create a minimal CatalogItem + SkuAlias.
    """
    code = _normalize(code)
    if not code:
        return None

    # Direct SKU match
    item = db.scalar(select(CatalogItem).where(CatalogItem.sku == code))
    if item:
        return BarcodeResolution(catalog_item=item, matched_on_alias=False, alias=None, created=False)

    # Alias lookup
    alias_row = db.scalar(select(SkuAlias).where(SkuAlias.alias == code))
    if alias_row:
        item = db.get(CatalogItem, alias_row.catalog_item_id)
        if item:
            return BarcodeResolution(catalog_item=item, matched_on_alias=True, alias=alias_row, created=False)

    if not auto_create:
        return None

    # Make first scan cheap: create placeholder CatalogItem + alias.
    item = CatalogItem(
        sku=code,
        name=code,
        unit=UnitEnum.EA,
        description=None,
        default_sell_price=None,
        default_cost=None,
        tax_category=None,
        is_active=True,
    )
    db.add(item)
    db.flush()  # allocate PK for alias FK

    alias = SkuAlias(
        catalog_item_id=item.id,
        alias=code,
        kind=AliasKindEnum.UPC,
        created_by=created_by,
    )
    db.add(alias)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # Another request might have created the catalog item concurrently.
        existing = resolve_catalog_item(db, code, auto_create=False)
        if existing:
            return BarcodeResolution(
                catalog_item=existing.catalog_item,
                matched_on_alias=existing.matched_on_alias,
                alias=existing.alias,
                created=False,
            )
        raise

    db.refresh(item)
    db.refresh(alias)
    return BarcodeResolution(catalog_item=item, matched_on_alias=False, alias=alias, created=True)


def ensure_alias(
    db: Session,
    *,
    catalog_item_id: int,
    alias_value: str,
    kind: AliasKindEnum = AliasKindEnum.UPC,
    created_by: str | None = None,
) -> SkuAlias:
    """
    Idempotently create an alias for a catalog item.
    """
    alias_value = _normalize(alias_value)
    if not alias_value:
        raise ValueError("Alias value is required.")

    existing = db.scalar(select(SkuAlias).where(SkuAlias.alias == alias_value))
    if existing:
        if existing.catalog_item_id != catalog_item_id:
            raise ValueError("Alias already bound to a different catalog item.")
        return existing

    alias = SkuAlias(
        catalog_item_id=catalog_item_id,
        alias=alias_value,
        kind=kind,
        created_by=created_by,
    )
    db.add(alias)
    db.commit()
    db.refresh(alias)
    return alias

