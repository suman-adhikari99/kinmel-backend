"""Add POS sales tables

Revision ID: 20250120_0001
Revises: 20250105_0010
Create Date: 2025-01-20 00:01:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20250120_0001"
down_revision = "20250105_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pos_sales",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("location_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("reserved_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["location_id"], ["locations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="uq_pos_sales_idempotency_key"),
    )
    op.create_index("ix_pos_sales_status", "pos_sales", ["status"])
    op.create_index("ix_pos_sales_reserved_until", "pos_sales", ["reserved_until"])

    op.create_table(
        "pos_sale_lines",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("sale_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("barcode", sa.String(length=50), nullable=False),
        sa.Column("sku", sa.String(length=50), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_price_at_sale", sa.Numeric(10, 2), nullable=False),
        sa.Column("tax_rate_at_sale", sa.Numeric(5, 4), nullable=False),
        sa.Column("name_snapshot", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["sale_id"], ["pos_sales.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_pos_sale_lines_sale", "pos_sale_lines", ["sale_id"])


def downgrade() -> None:
    op.drop_index("ix_pos_sale_lines_sale", table_name="pos_sale_lines")
    op.drop_table("pos_sale_lines")
    op.drop_index("ix_pos_sales_reserved_until", table_name="pos_sales")
    op.drop_index("ix_pos_sales_status", table_name="pos_sales")
    op.drop_table("pos_sales")
