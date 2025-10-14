# app/crud/hardware.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import select, desc

from ..models.inventory import InventoryEvent

from ..models.hardware import Hardware
from ..core.barcodes import barcode_aliases, normalize_barcode


def list_hardware(db: Session, limit: int = 100, offset: int = 0):
    """
    Return hardware items ordered by created_at (desc) with pagination.
    """
    stmt = (
        select(Hardware)
        .order_by(desc(Hardware.created_at))
        .limit(limit)
        .offset(offset)
    )
    items = db.execute(stmt).scalars().all()
    _normalize_existing_barcodes(db, items)
    _attach_inventory_metrics(db, items)
    return items


def get_hardware(db: Session, identifier: int | str) -> Hardware | None:
    """Fetch a single hardware record by id or barcode."""

    def _finalize(obj: Hardware | None) -> Hardware | None:
        if not obj:
            return None
        _normalize_existing_barcodes(db, [obj])
        _attach_inventory_metrics(db, [obj])
        return obj

    if isinstance(identifier, int):
        return _finalize(db.get(Hardware, identifier))

    lookup_value = str(identifier).strip()
    if not lookup_value:
        return None

    for candidate in barcode_aliases(lookup_value):
        stmt = select(Hardware).where(Hardware.barcode == candidate)
        match = db.execute(stmt).scalars().first()
        if match:
            return _finalize(match)

    if lookup_value.isdigit():
        try:
            as_int = int(lookup_value)
        except ValueError:
            as_int = None
        else:
            match = db.get(Hardware, as_int)
            if match:
                return _finalize(match)

    return None


def create_hardware(db: Session, payload: dict) -> Hardware:
    """
    Create and persist a hardware record from a payload dict.
    """
    data = payload.copy()
    barcode = normalize_barcode(data.get("barcode"))
    if not barcode:
        raise ValueError("barcode is required for hardware items")
    data["barcode"] = barcode

    if "description" in data and isinstance(data["description"], str):
        data["description"] = data["description"].strip()

    for key in ("acquisition_cost", "sales_price"):
        if key in data:
            val = (data[key] or "")
            data[key] = val.strip() or None

    data.setdefault(
        "created_at",
        datetime.utcnow().isoformat(timespec="seconds") + "Z",
    )

    obj = Hardware(**data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_hardware(db: Session, item: Hardware, payload: dict) -> Hardware:
    """
    Update an existing hardware record in-place from a payload dict.
    Unknown keys are ignored so older clients with stale fields do not break.
    """
    for k, v in payload.items():
        if not hasattr(item, k):
            continue
        if isinstance(v, str):
            if k == "barcode":
                v = normalize_barcode(v)
                if not v:
                    raise ValueError("barcode is required for hardware items")
            else:
                v = v.strip()
                if k in ("acquisition_cost", "sales_price") and v == "":
                    v = None
        elif k == "barcode" and v is None:
            raise ValueError("barcode is required for hardware items")
        setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


def delete_hardware(db: Session, item: Hardware) -> None:
    """
    Delete the given hardware record.
    """
    db.delete(item)
    db.commit()


def _attach_inventory_metrics(db: Session, items: list[Hardware]) -> None:
    if not items:
        return
    hardware_map = {item.id: item for item in items}
    if not hardware_map:
        return
    for item in hardware_map.values():
        setattr(item, "common_vendors", [])
        setattr(item, "average_unit_cost", None)

    hardware_ids = tuple(hardware_map.keys())
    stmt = (
        select(
            InventoryEvent.hardware_id,
            InventoryEvent.counterparty_name,
            InventoryEvent.unit_cost,
        )
        .where(
            InventoryEvent.hardware_id.in_(hardware_ids),
            InventoryEvent.counterparty_type == "vendor",
            InventoryEvent.change > 0,
        )
    )

    vendor_info: dict[int, dict[str, list]] = {}
    rows = db.execute(stmt).all()
    for hardware_id, counterparty_name, unit_cost in rows:
        info = vendor_info.setdefault(hardware_id, {"vendors": [], "unit_costs": []})
        name = (counterparty_name or "").strip()
        if name and name not in info["vendors"]:
            info["vendors"].append(name)
        if unit_cost is not None:
            info["unit_costs"].append(unit_cost)

    for hardware_id, info in vendor_info.items():
        item = hardware_map.get(hardware_id)
        if not item:
            continue
        if info["vendors"]:
            setattr(item, "common_vendors", info["vendors"])
        if info["unit_costs"]:
            avg = sum(info["unit_costs"]) / len(info["unit_costs"])
            setattr(item, "average_unit_cost", avg)


def _normalize_existing_barcodes(db: Session, items: list[Hardware]) -> None:
    if not items:
        return

    dirty = False
    for item in items:
        normalized = normalize_barcode(item.barcode)
        if not normalized or normalized == item.barcode:
            continue
        # Avoid collisions when two legacy rows normalize to the same value.
        conflict_stmt = select(Hardware.id).where(
            Hardware.id != item.id,
            Hardware.barcode == normalized,
        )
        conflict = db.execute(conflict_stmt).scalars().first()
        if conflict:
            continue
        item.barcode = normalized
        dirty = True

    if dirty:
        db.commit()
        for item in items:
            db.refresh(item)
