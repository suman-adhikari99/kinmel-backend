"""Add product image_file column

Revision ID: 20250105_0005
Revises: 20250105_0004
Create Date: 2025-01-05 00:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250105_0005"
down_revision = "20250105_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("image_file", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "image_file")
