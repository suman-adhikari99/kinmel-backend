"""Add categories table

Revision ID: 20250105_0006
Revises: 20250105_0005
Create Date: 2025-01-05 00:06:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250105_0006"
down_revision = "20250105_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("featured", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("image_file", sa.String(length=500), nullable=True),
        sa.UniqueConstraint("name", name="uq_categories_name"),
    )
    op.create_index("ix_categories_status", "categories", ["status"])
    op.create_index("ix_categories_featured", "categories", ["featured"])
    op.create_index("ix_categories_priority", "categories", ["priority"])


def downgrade() -> None:
    op.drop_index("ix_categories_priority", table_name="categories")
    op.drop_index("ix_categories_featured", table_name="categories")
    op.drop_index("ix_categories_status", table_name="categories")
    op.drop_table("categories")
