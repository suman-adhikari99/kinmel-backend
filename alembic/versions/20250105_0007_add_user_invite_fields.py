"""add user invite fields

Revision ID: 20250105_0007
Revises: 20250105_0006
Create Date: 2025-12-27 20:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20250105_0007"
down_revision = "20250105_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("invite_token", sa.String(length=64), nullable=True))
    op.add_column("users", sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_invite_token", "users", ["invite_token"])


def downgrade() -> None:
    op.drop_index("ix_users_invite_token", table_name="users")
    op.drop_column("users", "invite_expires_at")
    op.drop_column("users", "invite_token")
    op.drop_column("users", "invited_at")
