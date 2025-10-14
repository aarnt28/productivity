"""add sku_aliases table"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20251014_01"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "sku_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("hardware_id", sa.Integer(), sa.ForeignKey("hardware.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="UPC"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_sku_aliases_alias", "sku_aliases", ["alias"])

def downgrade() -> None:
    op.drop_constraint("uq_sku_aliases_alias", "sku_aliases", type_="unique")
    op.drop_table("sku_aliases")
