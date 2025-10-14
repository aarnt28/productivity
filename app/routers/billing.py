from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.billing import Invoice
from app.schemas.billing import (
    InvoiceCreateRequest,
    InvoiceFinalizeRequest,
    InvoiceOut,
    InvoiceStatus as InvoiceStatusSchema,
    UnbilledResponse,
)
from app.services.billing import BillingError, create_invoice as svc_create_invoice, finalize_invoice as svc_finalize_invoice, get_unbilled

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

