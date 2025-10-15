from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.deps.auth import api_auth
from app.models.catalog import CatalogItem, UnitEnum
from app.models.inventory import StockReferenceType, Warehouse
from app.models.work import (
    Client,
    LaborRole,
    PartUsage,
    Project,
    TimeEntry,
    WorkOrder,
    WorkOrderStatus,
)
from app.schemas.work import (
    PartIssueRequest,
    PartIssueResponse,
    PartUsageOut,
    QuickIssueRequest,
    QuickTimeStartRequest,
    TimeEntryOut,
    TimeEntryStartRequest,
    TimeEntryStopRequest,
    WorkOrderCreate,
    WorkOrderOut,
)
from app.services.barcode import resolve_catalog_item
from app.services.stock import StockError, issue_fifo
from app.services.clientsync import resolve_client_key, get_client_entry

router = APIRouter(prefix="/api/v2/work", tags=["work"], dependencies=[Depends(api_auth)])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_client(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _ensure_project(db: Session, project_id: Optional[int], client_id: int) -> Optional[Project]:
    if project_id is None:
        return None
    project = db.get(Project, project_id)
    if not project or project.client_id != client_id:
        raise HTTPException(status_code=404, detail="Project not found for client")
    return project


def _ensure_work_order(db: Session, work_order_id: int) -> WorkOrder:
    order = db.get(WorkOrder, work_order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Work order not found")
    return order


def _ensure_labor_role(db: Session, labor_role_id: int) -> LaborRole:
    role = db.get(LaborRole, labor_role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Labor role not found")
    return role


def _ensure_labor_role_by_name(db: Session, labor_role_name: str) -> LaborRole:
    name = (labor_role_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Labor role name is required")
    role = db.execute(select(LaborRole).where(LaborRole.name == name)).scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Labor role not found")
    return role


def _ensure_warehouse(db: Session, warehouse_id: int) -> Warehouse:
    warehouse = db.get(Warehouse, warehouse_id)
    if not warehouse:
        raise HTTPException(status_code=404, detail="Warehouse not found")
    return warehouse


def _ensure_default_warehouse(db: Session) -> Warehouse:
    rows = db.execute(select(Warehouse).where(Warehouse.is_active.is_(True)).order_by(Warehouse.id.asc())).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No active warehouses configured")
    if len(rows) > 1:
        raise HTTPException(status_code=400, detail="Multiple warehouses exist; specify warehouse_id")
    return rows[0]


def _find_or_create_client_by_name(db: Session, name: str) -> Client:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Client name is required")
    client = db.execute(select(Client).where(Client.name == name)).scalars().first()
    if client:
        return client
    client = Client(name=name)
    db.add(client)
    db.flush()
    return client


def _resolve_client_from_payload(db: Session, *, client_id: int | None, client_key: str | None, client_name: str | None) -> Client:
    if client_id:
        return _ensure_client(db, client_id)
    # Prefer explicit key -> name via client table
    if client_key:
        entry = get_client_entry(client_key)
        name = (entry or {}).get("name") or client_key
        return _find_or_create_client_by_name(db, name)
    # Accept raw name as last resort
    if client_name:
        # If the provided name maps to a known key, normalize to that table name
        key = resolve_client_key(client_name)
        if key:
            entry = get_client_entry(key) or {}
            normalized_name = entry.get("name") or client_name
            return _find_or_create_client_by_name(db, normalized_name)
        return _find_or_create_client_by_name(db, client_name)
    raise HTTPException(status_code=400, detail="Provide client_id, client_key, or client_name")


@router.post("/orders", response_model=WorkOrderOut, status_code=status.HTTP_201_CREATED)
def create_work_order(payload: WorkOrderCreate, db: Session = Depends(get_db)):
    client = _ensure_client(db, payload.client_id)
    project = _ensure_project(db, payload.project_id, client.id)
    order = WorkOrder(
        client_id=client.id,
        project_id=project.id if project else None,
        title=payload.title,
        description=payload.description,
        status=WorkOrderStatus.OPEN,
        opened_at=datetime.utcnow(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def _find_or_create_active_order(
    db: Session,
    *,
    client_id: int,
    project_id: Optional[int],
    title_hint: Optional[str] = None,
) -> WorkOrder:
    stmt = (
        select(WorkOrder)
        .where(
            WorkOrder.client_id == client_id,
            WorkOrder.status.in_([WorkOrderStatus.OPEN, WorkOrderStatus.IN_PROGRESS]),
        )
        .order_by(WorkOrder.opened_at.desc())
    )
    if project_id:
        stmt = stmt.where(WorkOrder.project_id == project_id)
    order = db.execute(stmt).scalars().first()
    if order:
        return order

    client = _ensure_client(db, client_id)
    project = _ensure_project(db, project_id, client_id) if project_id else None
    order = WorkOrder(
        client_id=client.id,
        project_id=project.id if project else None,
        title=title_hint or f"Work order for {client.name}",
        status=WorkOrderStatus.OPEN,
        opened_at=datetime.utcnow(),
    )
    db.add(order)
    db.flush()
    return order


@router.post("/time/start", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def start_time(payload: TimeEntryStartRequest, db: Session = Depends(get_db)):
    labor_role = _ensure_labor_role(db, payload.labor_role_id)

    if payload.work_order_id:
        order = _ensure_work_order(db, payload.work_order_id)
    else:
        if not payload.client_id:
            raise HTTPException(status_code=400, detail="client_id required when work_order_id absent")
        order = _find_or_create_active_order(
            db,
            client_id=payload.client_id,
            project_id=payload.project_id,
            title_hint=f"Work order for client {payload.client_id}",
        )

    if order.status == WorkOrderStatus.OPEN:
        order.status = WorkOrderStatus.IN_PROGRESS
        db.add(order)

    entry = TimeEntry(
        work_order_id=order.id,
        labor_role_id=labor_role.id,
        user_id=payload.user_id,
        started_at=payload.started_at or datetime.utcnow(),
        ended_at=None,
        minutes=0,
        bill_rate_override=payload.bill_rate_override,
        cost_rate_override=payload.cost_rate_override,
        billable=True,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/time/stop", response_model=TimeEntryOut)
def stop_time(payload: TimeEntryStopRequest, db: Session = Depends(get_db)):
    if payload.time_entry_id:
        entry = db.get(TimeEntry, payload.time_entry_id)
    else:
        entry = (
            db.execute(
                select(TimeEntry).where(TimeEntry.ended_at.is_(None)).order_by(TimeEntry.started_at.desc())
            )
            .scalars()
            .first()
        )
    if not entry:
        raise HTTPException(status_code=404, detail="No running time entry found")
    if entry.ended_at:
        return entry

    end_ts = payload.ended_at or datetime.utcnow()
    if entry.started_at:
        duration = end_ts - entry.started_at
        minutes = max(int(duration.total_seconds() // 60), 1)
    else:
        minutes = 1
    entry.ended_at = end_ts
    entry.minutes = minutes
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def _build_part_usage_out(usage: PartUsage, item: CatalogItem) -> PartUsageOut:
    total_cost = Decimal(usage.qty) * Decimal(usage.unit_cost_resolved or 0)
    unit = item.unit.value if isinstance(item.unit, UnitEnum) else str(item.unit)
    return PartUsageOut(
        id=usage.id,
        work_order_id=usage.work_order_id,
        catalog_item_id=usage.catalog_item_id,
        warehouse_id=usage.warehouse_id,
        qty=Decimal(usage.qty),
        unit_cost_resolved=Decimal(usage.unit_cost_resolved or 0),
        sell_price_override=usage.sell_price_override,
        total_cost=total_cost,
        sku=item.sku,
        name=item.name,
        unit=unit,
    )


@router.post("/parts/issue", response_model=PartIssueResponse, status_code=status.HTTP_201_CREATED)
def issue_part(payload: PartIssueRequest, db: Session = Depends(get_db)):
    order = _ensure_work_order(db, payload.work_order_id)
    warehouse = _ensure_warehouse(db, payload.warehouse_id)

    resolved = resolve_catalog_item(db, payload.alias, created_by=payload.created_by)
    if not resolved:
        raise HTTPException(status_code=404, detail="Alias could not be resolved")
    item = resolved.catalog_item

    usage = PartUsage(
        work_order_id=order.id,
        catalog_item_id=item.id,
        warehouse_id=warehouse.id,
        qty=Decimal(payload.qty),
        sell_price_override=None,
        unit_cost_resolved=None,
        barcode_scanned=payload.barcode_scanned,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    db.add(usage)
    db.flush()

    try:
        issue_result = issue_fifo(
            db,
            warehouse=warehouse,
            catalog_item=item,
            qty=Decimal(payload.qty),
            reference_type=StockReferenceType.WORK_ENTRY,
            reference_id=str(usage.id),
            created_by=payload.created_by,
        )
    except StockError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    usage.unit_cost_resolved = issue_result.average_cost
    db.add(usage)
    db.commit()
    db.refresh(usage)
    for entry in issue_result.ledger_entries:
        db.refresh(entry)

    usage_out = _build_part_usage_out(usage, item)
    return PartIssueResponse(usage=usage_out, ledger_entries=issue_result.ledger_entries)


@router.post("/items/quick-issue", response_model=PartIssueResponse, status_code=status.HTTP_201_CREATED)
def quick_issue_item(payload: QuickIssueRequest, db: Session = Depends(get_db)):
    # Resolve or create target work order
    if payload.work_order_id:
        order = _ensure_work_order(db, payload.work_order_id)
    else:
        client = _resolve_client_from_payload(
            db,
            client_id=payload.client_id,
            client_key=payload.client_key,
            client_name=payload.client_name,
        )
        order = _find_or_create_active_order(
            db,
            client_id=client.id,
            project_id=payload.project_id,
            title_hint=f"Work order for {client.name}",
        )

    # Resolve warehouse
    if payload.warehouse_id:
        warehouse = _ensure_warehouse(db, payload.warehouse_id)
    else:
        warehouse = _ensure_default_warehouse(db)

    # Resolve item (auto-creates placeholder on first scan)
    resolved = resolve_catalog_item(db, payload.alias, created_by=payload.created_by)
    if not resolved:
        raise HTTPException(status_code=404, detail="Alias could not be resolved")
    item = resolved.catalog_item

    # Create PartUsage and issue stock FIFO
    usage = PartUsage(
        work_order_id=order.id,
        catalog_item_id=item.id,
        warehouse_id=warehouse.id,
        qty=Decimal(payload.qty),
        sell_price_override=None,
        unit_cost_resolved=None,
        barcode_scanned=payload.barcode_scanned,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    db.add(usage)
    db.flush()

    try:
        issue_result = issue_fifo(
            db,
            warehouse=warehouse,
            catalog_item=item,
            qty=Decimal(payload.qty),
            reference_type=StockReferenceType.WORK_ENTRY,
            reference_id=str(usage.id),
            created_by=payload.created_by,
        )
    except StockError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    usage.unit_cost_resolved = issue_result.average_cost
    db.add(usage)
    db.commit()
    db.refresh(usage)
    for entry in issue_result.ledger_entries:
        db.refresh(entry)

    usage_out = _build_part_usage_out(usage, item)
    return PartIssueResponse(usage=usage_out, ledger_entries=issue_result.ledger_entries)


@router.post("/time/quick-start", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
def quick_time_start(payload: QuickTimeStartRequest, db: Session = Depends(get_db)):
    # Resolve client and ensure an active work order
    client = _resolve_client_from_payload(
        db,
        client_id=payload.client_id,
        client_key=payload.client_key,
        client_name=payload.client_name,
    )
    order = _find_or_create_active_order(
        db,
        client_id=client.id,
        project_id=payload.project_id,
        title_hint=f"Work order for {client.name}",
    )

    # Resolve labor role
    if payload.labor_role_id:
        role = _ensure_labor_role(db, payload.labor_role_id)
    elif payload.labor_role_name:
        role = _ensure_labor_role_by_name(db, payload.labor_role_name)
    else:
        raise HTTPException(status_code=400, detail="labor_role_id or labor_role_name is required")

    entry = TimeEntry(
        work_order_id=order.id,
        labor_role_id=role.id,
        user_id=payload.user_id,
        started_at=payload.started_at or datetime.utcnow(),
        ended_at=None,
        minutes=0,
        bill_rate_override=payload.bill_rate_override,
        cost_rate_override=payload.cost_rate_override,
        billable=True,
        notes=payload.notes,
        created_by=payload.created_by,
    )
    db.add(entry)
    # Mark order in-progress if needed
    if order.status == WorkOrderStatus.OPEN:
        order.status = WorkOrderStatus.IN_PROGRESS
        db.add(order)
    db.commit()
    db.refresh(entry)
    return entry
