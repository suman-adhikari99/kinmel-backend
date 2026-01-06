"""add notifications tables

Revision ID: 20250105_0009
Revises: 20250105_0008
Create Date: 2025-12-28 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250105_0009"
down_revision = "20250105_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.String(length=50), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("source_label", sa.String(length=100), nullable=True),
        sa.Column("source_href", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_index("ix_notifications_type", "notifications", ["type"])
    op.create_index("ix_notifications_tenant_id", "notifications", ["tenant_id"])

    op.create_table(
        "notification_reads",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["notification_id"], ["notifications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_reads_notification_user"),
    )
    op.create_index("ix_notification_reads_user", "notification_reads", ["user_id"])
    op.create_index("ix_notification_reads_notification", "notification_reads", ["notification_id"])


def downgrade() -> None:
    op.drop_index("ix_notification_reads_notification", table_name="notification_reads")
    op.drop_index("ix_notification_reads_user", table_name="notification_reads")
    op.drop_table("notification_reads")
    op.drop_index("ix_notifications_tenant_id", table_name="notifications")
    op.drop_index("ix_notifications_type", table_name="notifications")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_table("notifications")
