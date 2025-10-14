"""three-layer data model"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = "20251014_02"
down_revision = "20251014_01"
branch_labels = None
depends_on = None


def _create_enum(name: str, *values: str) -> sa.Enum:
    enum_type = sa.Enum(*values, name=name)
    enum_type.create(op.get_bind(), checkfirst=True)
    return enum_type


def _drop_enum(enum: sa.Enum) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        enum.drop(bind, checkfirst=True)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "sku_aliases" in existing_tables:
        op.rename_table("sku_aliases", "sku_aliases_hardware")

    catalog_unit_enum = _create_enum("catalog_item_unit", "ea", "hour", "ft", "flat")
    sku_alias_kind_enum = _create_enum("sku_alias_kind", "UPC", "EAN", "MPN", "VendorSKU")
    stock_reason_enum = _create_enum("stock_reason", "RECEIPT", "ADJUST", "ISSUE", "RETURN")
    stock_reference_enum = _create_enum("stock_reference_type", "WorkEntry", "PO", "Init")
    project_status_enum = _create_enum("project_status", "active", "on_hold", "completed")
    work_order_status_enum = _create_enum("work_order_status", "open", "in_progress", "closed", "cancelled")
    invoice_status_enum = _create_enum("invoice_status", "draft", "sent", "paid")
    invoice_line_type_enum = _create_enum("invoice_line_type", "labor", "part", "flat")
    invoice_source_type_enum = _create_enum("invoice_source_type", "time_entry", "part_usage", "flat_task")

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("unit", catalog_unit_enum, nullable=False),
        sa.Column("default_sell_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("default_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("tax_category", sa.String(length=64), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("sku", name="uq_catalog_items_sku"),
        sa.CheckConstraint("sku <> ''", name="ck_catalog_items_sku_nonempty"),
        sa.CheckConstraint("default_sell_price >= 0", name="ck_catalog_items_sell_price_nonnegative"),
        sa.CheckConstraint("default_cost >= 0", name="ck_catalog_items_cost_nonnegative"),
    )

    op.create_table(
        "labor_roles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("bill_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_rate", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.UniqueConstraint("name", name="uq_labor_roles_name"),
    )

    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_warehouses_name_unique", "warehouses", ["name"], unique=True)

    op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_clients_name_unique", "clients", ["name"], unique=True)

    op.create_table(
        "flat_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("default_minutes", sa.Integer(), nullable=True),
        sa.Column("included_parts_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", project_status_enum, nullable=False, server_default="active"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_projects_name", "projects", ["name"])

    op.create_table(
        "sku_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("kind", sku_alias_kind_enum, nullable=False, server_default="UPC"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("alias", name="uq_sku_aliases_alias"),
        sa.CheckConstraint("alias <> ''", name="ck_sku_aliases_alias_nonempty"),
    )

    op.create_table(
        "inventory_lots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("qty_on_hand", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("unit_cost", sa.Numeric(14, 4), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("supplier", sa.String(length=128), nullable=True),
        sa.Column("lot_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("qty_on_hand >= 0", name="ck_inventory_lots_qty_nonnegative"),
    )
    op.create_index("ix_inventory_lots_catalog_warehouse", "inventory_lots", ["catalog_item_id", "warehouse_id"])

    op.create_table(
        "stock_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("inventory_lot_id", sa.Integer(), sa.ForeignKey("inventory_lots.id", ondelete="SET NULL"), nullable=True),
        sa.Column("qty_delta", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_cost_at_move", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("reason", stock_reason_enum, nullable=False),
        sa.Column("reference_type", stock_reference_enum, nullable=False),
        sa.Column("reference_id", sa.String(length=64), nullable=True),
        sa.Column("moved_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint("qty_delta <> 0", name="ck_stock_ledger_qty_nonzero"),
    )
    op.create_index("ix_stock_ledger_catalog_item_id", "stock_ledger", ["catalog_item_id"])
    op.create_index("ix_stock_ledger_warehouse_id", "stock_ledger", ["warehouse_id"])

    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("opened_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("status", work_order_status_enum, nullable=False, server_default="open"),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
        sa.CheckConstraint("title <> ''", name="ck_work_orders_title_nonempty"),
    )
    op.create_index("ix_work_orders_status", "work_orders", ["status"])

    op.create_table(
        "time_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("labor_role_id", sa.Integer(), sa.ForeignKey("labor_roles.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bill_rate_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_rate_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint("minutes >= 0", name="ck_time_entries_minutes_nonnegative"),
    )
    op.create_index("ix_time_entries_work_order_id", "time_entries", ["work_order_id"])

    op.create_table(
        "part_usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catalog_item_id", sa.Integer(), sa.ForeignKey("catalog_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("sell_price_override", sa.Numeric(12, 2), nullable=True),
        sa.Column("unit_cost_resolved", sa.Numeric(14, 4), nullable=True),
        sa.Column("barcode_scanned", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by", sa.String(length=64), nullable=True),
        sa.CheckConstraint("qty > 0", name="ck_part_usage_qty_positive"),
    )
    op.create_index("ix_part_usage_work_order_id", "part_usage", ["work_order_id"])
    op.create_index("ix_part_usage_catalog_item_id", "part_usage", ["catalog_item_id"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.Integer(), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("status", invoice_status_enum, nullable=False, server_default="draft"),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("tax", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("terms", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(length=64), nullable=True),
    )
    op.create_index("ix_invoices_status", "invoices", ["status"])

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("line_type", invoice_line_type_enum, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("qty", sa.Numeric(12, 4), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("line_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("source_type", invoice_source_type_enum, nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_invoice_lines_invoice_id", "invoice_lines", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_invoice_id", table_name="invoice_lines")
    op.drop_table("invoice_lines")
    op.drop_index("ix_invoices_status", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_part_usage_catalog_item_id", table_name="part_usage")
    op.drop_index("ix_part_usage_work_order_id", table_name="part_usage")
    op.drop_table("part_usage")
    op.drop_index("ix_time_entries_work_order_id", table_name="time_entries")
    op.drop_table("time_entries")
    op.drop_index("ix_work_orders_status", table_name="work_orders")
    op.drop_table("work_orders")
    op.drop_index("ix_stock_ledger_warehouse_id", table_name="stock_ledger")
    op.drop_index("ix_stock_ledger_catalog_item_id", table_name="stock_ledger")
    op.drop_table("stock_ledger")
    op.drop_index("ix_inventory_lots_catalog_warehouse", table_name="inventory_lots")
    op.drop_table("inventory_lots")
    op.drop_table("sku_aliases")
    op.drop_index("ix_projects_name", table_name="projects")
    op.drop_table("projects")
    op.drop_table("flat_tasks")
    op.drop_index("ix_clients_name_unique", table_name="clients")
    op.drop_table("clients")
    op.drop_index("ix_warehouses_name_unique", table_name="warehouses")
    op.drop_table("warehouses")
    op.drop_table("labor_roles")
    op.drop_table("catalog_items")

    bind = op.get_bind()
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    if "sku_aliases_hardware" in existing_tables:
        op.rename_table("sku_aliases_hardware", "sku_aliases")

    for enum_name in (
        "invoice_source_type",
        "invoice_line_type",
        "invoice_status",
        "work_order_status",
        "project_status",
        "stock_reference_type",
        "stock_reason",
        "sku_alias_kind",
        "catalog_item_unit",
    ):
        _drop_enum(sa.Enum(name=enum_name))
