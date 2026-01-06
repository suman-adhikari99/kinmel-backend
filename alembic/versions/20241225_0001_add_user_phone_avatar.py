"""Add phone and avatar_url columns to users table

Revision ID: 20241225_0001
Revises: 20241214_0001
Create Date: 2024-12-25

This migration adds:
- phone: Optional phone number field (max 20 chars)
- avatar_url: Optional profile picture URL (max 500 chars)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20241225_0001"
down_revision: Union[str, None] = "20241214_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add phone and avatar_url columns to users table."""
    op.add_column(
        "users",
        sa.Column("phone", sa.String(20), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Remove phone and avatar_url columns from users table."""
    op.drop_column("users", "avatar_url")
    op.drop_column("users", "phone")

