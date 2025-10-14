from __future__ import annotations
from typing import Iterable
from sqlalchemy import text
from sqlalchemy.engine import Engine

# Simple, idempotent migrations for SQLite.
# We only ADD/reshape tables when required. No destructive column drops without a copy step.


def _table_columns(engine: Engine, table: str) -> list[dict[str, object]]:
    with engine.connect() as conn:
        return conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()


def _column_names(engine: Engine, table: str) -> set[str]:
    return {row["name"] for row in _table_columns(engine, table)}


def _add_column_sqlite(engine: Engine, table: str, col_def: str) -> None:
    """ALTER TABLE ADD COLUMN helper."""
    with engine.begin() as conn:
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_def}"))


def _create_index_if_not_exists(engine: Engine, table: str, name: str, cols: Iterable[str], unique: bool = False) -> None:
    cols_sql = ", ".join(cols)
    unique_sql = "UNIQUE " if unique else ""
    with engine.begin() as conn:
        conn.execute(text(f"CREATE {unique_sql}INDEX IF NOT EXISTS {name} ON {table} ({cols_sql})"))


def _rebuild_hardware_table(engine: Engine) -> None:
    """
    Recreate the hardware table without legacy client/client_key/completed columns.
    Existing rows are copied over, filling barcodes when missing.
    """
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS hardware__new (
                    id INTEGER PRIMARY KEY,
                    barcode TEXT NOT NULL,
                    description TEXT NOT NULL,
                    acquisition_cost TEXT,
                    sales_price TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT OR REPLACE INTO hardware__new (id, barcode, description, acquisition_cost, sales_price, created_at)
                SELECT
                    id,
                    CASE WHEN barcode IS NULL OR barcode = '' THEN 'HW-' || id ELSE barcode END,
                    description,
                    acquisition_cost,
                    sales_price,
                    COALESCE(created_at, datetime('now'))
                FROM hardware
                """
            )
        )
        conn.execute(text("DROP TABLE hardware"))
        conn.execute(text("ALTER TABLE hardware__new RENAME TO hardware"))


def run_migrations(engine: Engine) -> None:
    """
    Adds ticket columns introduced by the dynamic tickets feature and keeps hardware schema current.
    """
    ticket_needed: dict[str, str] = {
        "hardware_id": "INTEGER",
        "hardware_description": "TEXT",
        "hardware_sales_price": "TEXT",
        "hardware_quantity": "INTEGER",
        "sent": "INTEGER DEFAULT 0 NOT NULL",
        "invoiced_total": "TEXT",
        "calculated_value": "TEXT",
    }

    # Tickets table incremental columns
    tcols = _column_names(engine, "tickets")
    for name, dtype in ticket_needed.items():
        if name not in tcols:
            _add_column_sqlite(engine, "tickets", f"{name} {dtype}")

    # Hardware schema upgrades
    hcols = _column_names(engine, "hardware")
    if not hcols:
        # Table absent -> nothing to migrate; Base.metadata.create_all will create fresh schema.
        return

    legacy_cols = {"client", "client_key", "completed"}
    if legacy_cols & hcols:
        _rebuild_hardware_table(engine)
        hcols = _column_names(engine, "hardware")

    if "barcode" not in hcols:
        _add_column_sqlite(engine, "hardware", "barcode TEXT")

    # Ensure all rows have a barcode value
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE hardware SET barcode = CASE WHEN barcode IS NULL OR barcode = '' THEN 'HW-' || id ELSE barcode END")
        )

    _create_index_if_not_exists(engine, "hardware", "ix_hardware_barcode_unique", ["barcode"], unique=True)

    # Inventory event enrichments (vendor/client + costing)
    inventory_table = _table_columns(engine, "inventory_events")
    if inventory_table:
        inventory_cols = {row["name"] for row in inventory_table}
        new_cols = {
            "counterparty_name": "TEXT",
            "counterparty_type": "TEXT",
            "actual_cost": "REAL",
            "unit_cost": "REAL",
            "sale_price_total": "REAL",
            "sale_unit_price": "REAL",
        }
        for name, dtype in new_cols.items():
            if name not in inventory_cols:
                _add_column_sqlite(engine, "inventory_events", f"{name} {dtype}")