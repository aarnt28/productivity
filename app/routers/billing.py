from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.billing import Invoice
from app.models.catalog import CatalogItem, FlatTask
from app.models.work import Client
from app.schemas.billing import (
    InvoiceCreateRequest,
    InvoiceFinalizeRequest,
    InvoiceOut,
    InvoiceStatus as InvoiceStatusSchema,
    InvoiceLineCreate,
    InvoiceLineType,
    InvoiceSourceType,
    QuickFlatRequest,
    UnbilledResponse,
)
from app.services.billing import BillingError, create_invoice as svc_create_invoice, finalize_invoice as svc_finalize_invoice, get_unbilled
from app.services.barcode import resolve_catalog_item
from app.services.clientsync import resolve_client_key, get_client_entry

router = APIRouter(prefix="/api/billing", tags=["billing"], dependencies=[Depends(api_auth)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
    db.close()


@router.get("/unbilled", response_model=UnbilledResponse)
def unbilled(client_id: int | None = None, db: Session = Depends(get_db)):
    return get_unbilled(db, client_id)


@router.post("/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def create_invoice(payload: InvoiceCreateRequest, db: Session = Depends(get_db)):
    try:
        invoice = svc_create_invoice(db, payload)
        db.commit()
        db.refresh(invoice)
        return invoice
    except BillingError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/invoices/{invoice_id}/finalize", response_model=InvoiceOut)
def finalize_invoice(invoice_id: int, payload: InvoiceFinalizeRequest, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    try:
        invoice = svc_finalize_invoice(db, invoice, payload.status)
        db.commit()
        db.refresh(invoice)
    except BillingError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return invoice


def _ensure_client_for_billing(db: Session, *, client_id: int | None, client_key: str | None, client_name: str | None) -> Client:
    if client_id:
        client = db.get(Client, client_id)
        if not client:
            raise HTTPException(status_code=404, detail="Client not found")
        return client
    name = None
    if client_key:
        entry = get_client_entry(client_key)
        if not entry:
            raise HTTPException(status_code=404, detail="Unknown client_key")
        name = entry.get("name") or client_key
    elif client_name:
        # normalize against client table if present
        key = resolve_client_key(client_name)
        if key:
            entry = get_client_entry(key)
            name = (entry or {}).get("name") or client_name
        else:
            name = client_name
    if not name:
        raise HTTPException(status_code=400, detail="Provide client_id, client_key, or client_name")
    existing = db.execute(select(Client).where(Client.name == name)).scalars().first()
    if existing:
        return existing
    newc = Client(name=name)
    db.add(newc)
    db.flush()
    return newc


@router.post("/quick-flat", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
def quick_flat(payload: QuickFlatRequest, db: Session = Depends(get_db)):
    client = _ensure_client_for_billing(
        db,
        client_id=payload.client_id,
        client_key=payload.client_key,
        client_name=payload.client_name,
    )

    # Resolve catalog item
    item: CatalogItem | None = None
    if payload.catalog_item_id:
        item = db.get(CatalogItem, payload.catalog_item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Catalog item not found")
    elif payload.alias:
        resolved = resolve_catalog_item(db, payload.alias, created_by=payload.created_by)
        if not resolved:
            raise HTTPException(status_code=404, detail="Alias could not be resolved")
        item = resolved.catalog_item
    else:
        raise HTTPException(status_code=400, detail="Provide catalog_item_id or alias")

    # Determine line details
    description = (payload.description or item.name or item.sku).strip()
    unit_price = payload.unit_price if payload.unit_price is not None else item.default_sell_price
    if unit_price is None:
        raise HTTPException(status_code=422, detail="unit_price is required when item has no default_sell_price")

    # Create a per-use FlatTask as the invoice source anchor
    ft = FlatTask(catalog_item_id=item.id)
    db.add(ft)
    db.flush()

    line = InvoiceLineCreate(
        line_type=InvoiceLineType.FLAT,
        description=description,
        qty=payload.qty,
        unit_price=unit_price,
        source_type=InvoiceSourceType.FLAT_TASK,
        source_id=ft.id,
    )
    req = InvoiceCreateRequest(
        client_id=client.id,
        lines=[line],
        tax=payload.tax,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    try:
        invoice = svc_create_invoice(db, req)
        db.commit()
        db.refresh(invoice)
        return invoice
    except BillingError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
