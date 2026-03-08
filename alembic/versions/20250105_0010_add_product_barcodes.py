"""Add product barcodes table

Revision ID: 20250105_0010
Revises: 20250105_0009
Create Date: 2025-01-05 00:10:00.000000
"""

from __future__ import annotations

from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20250105_0010"
down_revision = "20250105_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_barcodes",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("barcode", sa.String(length=50), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("barcode", name="uq_product_barcodes_barcode"),
    )
    op.create_index("ix_product_barcodes_product", "product_barcodes", ["product_id"])

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, barcode, created_at, updated_at "
            "FROM products WHERE barcode IS NOT NULL AND barcode <> ''"
        )
    ).fetchall()
    if rows:
        barcode_table = sa.table(
            "product_barcodes",
            sa.column("id", postgresql.UUID(as_uuid=False)),
            sa.column("product_id", postgresql.UUID(as_uuid=False)),
            sa.column("barcode", sa.String(length=50)),
            sa.column("is_primary", sa.Boolean()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            barcode_table,
            [
                {
                    "id": str(uuid4()),
                    "product_id": row.id,
                    "barcode": row.barcode,
                    "is_primary": True,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ],
        )


def downgrade() -> None:
    op.drop_index("ix_product_barcodes_product", table_name="product_barcodes")
    op.drop_table("product_barcodes")
