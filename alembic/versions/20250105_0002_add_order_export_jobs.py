"""Add order export jobs table

Revision ID: 20250105_0002
Revises: 20250105_0001
Create Date: 2025-01-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250105_0002"
down_revision: Union[str, None] = "20250105_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create order export jobs table."""
    op.create_table(
        "order_export_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.Column("requested_by", sa.String(36), nullable=False),
        sa.Column("destination_email", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("filters_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("file_url", sa.String(500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_order_export_jobs_status",
        "order_export_jobs",
        ["status"],
    )
    op.create_index(
        "ix_order_export_jobs_requested_by",
        "order_export_jobs",
        ["requested_by"],
    )


def downgrade() -> None:
    """Drop order export jobs table."""
    op.drop_index("ix_order_export_jobs_requested_by", table_name="order_export_jobs")
    op.drop_index("ix_order_export_jobs_status", table_name="order_export_jobs")
    op.drop_table("order_export_jobs")
