"""Add product fields for UI filters

Revision ID: 20250105_0004
Revises: 20250105_0003
Create Date: 2025-01-05 00:04:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250105_0004"
down_revision = "20250105_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("subcategory", sa.String(length=100), nullable=True))
    op.add_column("products", sa.Column("image_url", sa.String(length=500), nullable=True))
    op.add_column(
        "products",
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
    )
    op.add_column(
        "products",
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "products",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_featured", "products", ["featured"])
    op.create_index("ix_products_priority", "products", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_products_priority", table_name="products")
    op.drop_index("ix_products_featured", table_name="products")
    op.drop_index("ix_products_status", table_name="products")
    op.drop_column("products", "priority")
    op.drop_column("products", "featured")
    op.drop_column("products", "status")
    op.drop_column("products", "image_url")
    op.drop_column("products", "subcategory")
