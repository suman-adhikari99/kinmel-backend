"""Add revenue tables

Revision ID: 20250105_0003
Revises: 20250105_0002
Create Date: 2025-01-05
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250105_0003"
down_revision: Union[str, None] = "20250105_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revenue_payments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("method", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="completed"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_revenue_payments_amount_non_negative"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_revenue_payments_order_id", "revenue_payments", ["order_id"])
    op.create_index("ix_revenue_payments_status", "revenue_payments", ["status"])
    op.create_index("ix_revenue_payments_method", "revenue_payments", ["method"])

    op.create_table(
        "revenue_payouts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("payout_at", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("amount >= 0", name="ck_revenue_payouts_amount_non_negative"),
    )
    op.create_index("ix_revenue_payouts_status", "revenue_payouts", ["status"])
    op.create_index("ix_revenue_payouts_payout_at", "revenue_payouts", ["payout_at"])

    op.create_table(
        "revenue_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("adjustment_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("amount >= 0", name="ck_revenue_adjustments_amount_non_negative"),
    )
    op.create_index("ix_revenue_adjustments_type", "revenue_adjustments", ["adjustment_type"])

    op.create_table(
        "business_profile",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("legal_name", sa.String(200), nullable=False),
        sa.Column("abn", sa.String(30), nullable=False),
        sa.Column("gst_registered", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("gst_rate", sa.String(10), nullable=False),
        sa.Column("store_address", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(200), nullable=False),
        sa.Column("contact_phone", sa.String(50), nullable=False),
        sa.Column("bank_masked", sa.String(50), nullable=False),
        sa.Column("payout_frequency", sa.String(30), nullable=False, server_default="Daily"),
        sa.Column("processor", sa.String(50), nullable=False, server_default="Stripe"),
    )


def downgrade() -> None:
    op.drop_table("business_profile")
    op.drop_index("ix_revenue_adjustments_type", table_name="revenue_adjustments")
    op.drop_table("revenue_adjustments")
    op.drop_index("ix_revenue_payouts_payout_at", table_name="revenue_payouts")
    op.drop_index("ix_revenue_payouts_status", table_name="revenue_payouts")
    op.drop_table("revenue_payouts")
    op.drop_index("ix_revenue_payments_method", table_name="revenue_payments")
    op.drop_index("ix_revenue_payments_status", table_name="revenue_payments")
    op.drop_index("ix_revenue_payments_order_id", table_name="revenue_payments")
    op.drop_table("revenue_payments")
