"""add report exports table

Revision ID: 20250105_0008
Revises: 20250105_0007
Create Date: 2025-12-27 20:25:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20250105_0008"
down_revision = "20250105_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_exports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("report_id", sa.String(length=50), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=500), nullable=True),
        sa.Column("size_kb", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_exports_report_id", "report_exports", ["report_id"])
    op.create_index("ix_report_exports_status", "report_exports", ["status"])


def downgrade() -> None:
    op.drop_index("ix_report_exports_status", table_name="report_exports")
    op.drop_index("ix_report_exports_report_id", table_name="report_exports")
    op.drop_table("report_exports")
