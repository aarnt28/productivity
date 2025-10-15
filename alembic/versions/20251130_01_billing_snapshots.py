"""add billing snapshot fields

Revision ID: 20251130_01
Revises: 20251014_02_three_layer_model
Create Date: 2025-11-30 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251130_01"
down_revision = "20251014_02_three_layer_model"
branch_labels = None
depends_on = None


billing_state_enum = sa.Enum(
    "open",
    "awaiting_approval",
    "ready_to_bill",
    "invoiced",
    "closed",
    name="work_order_billing_state",
)


def upgrade() -> None:
    op.add_column(
        "time_entries",
        sa.Column("snap_cost_rate", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "time_entries",
        sa.Column("snap_bill_rate", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "time_entries",
        sa.Column(
            "write_off_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "time_entries",
        sa.Column("approved_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "time_entries",
        sa.Column("approved_by", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "part_usage",
        sa.Column("snap_unit_cost", sa.Numeric(12, 4), nullable=True),
    )
    op.add_column(
        "part_usage",
        sa.Column("snap_unit_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "part_usage",
        sa.Column(
            "write_off_amount",
            sa.Numeric(12, 2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "invoice_lines",
        sa.Column("unit_cost", sa.Numeric(12, 4), nullable=True),
    )
    op.add_column(
        "invoice_lines",
        sa.Column("tax_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "invoice_lines",
        sa.Column("snapshot_json", sa.Text(), nullable=True),
    )
    billing_state_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "work_orders",
        sa.Column(
            "billing_state",
            billing_state_enum,
            nullable=False,
            server_default="open",
        ),
    )
    op.alter_column(
        "time_entries",
        "write_off_amount",
        server_default=None,
    )
    op.alter_column(
        "part_usage",
        "write_off_amount",
        server_default=None,
    )
    op.alter_column(
        "work_orders",
        "billing_state",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("work_orders", "billing_state")
    billing_state_enum.drop(op.get_bind(), checkfirst=True)
    op.drop_column("invoice_lines", "snapshot_json")
    op.drop_column("invoice_lines", "tax_code")
    op.drop_column("invoice_lines", "unit_cost")
    op.drop_column("part_usage", "write_off_amount")
    op.drop_column("part_usage", "snap_unit_price")
    op.drop_column("part_usage", "snap_unit_cost")
    op.drop_column("time_entries", "approved_by")
    op.drop_column("time_entries", "approved_at")
    op.drop_column("time_entries", "write_off_amount")
    op.drop_column("time_entries", "snap_bill_rate")
    op.drop_column("time_entries", "snap_cost_rate")
