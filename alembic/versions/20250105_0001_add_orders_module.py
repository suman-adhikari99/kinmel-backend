"""Add order management tables

Revision ID: 20250105_0001
Revises: 20241225_0001
Create Date: 2025-01-05

This migration adds:
- orders
- order_items
- order_item_substitutions
- order_status_history
- order_contact_attempts
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250105_0001"
down_revision: Union[str, None] = "20241225_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create order management tables."""
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
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
        sa.Column("order_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="new"),
        sa.Column("time_slot", sa.String(50), nullable=True),
        sa.Column("customer_name", sa.String(200), nullable=False),
        sa.Column("customer_phone", sa.String(50), nullable=False),
        sa.Column("customer_email", sa.String(200), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("delivery_suburb", sa.String(100), nullable=True),
        sa.Column("subtotal", sa.Numeric(12, 2), nullable=False),
        sa.Column("gst", sa.Numeric(12, 2), nullable=False),
        sa.Column("delivery_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("total", sa.Numeric(12, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("has_substitutions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        sa.CheckConstraint("gst >= 0", name="ck_orders_gst_non_negative"),
        sa.CheckConstraint("delivery_fee >= 0", name="ck_orders_delivery_fee_non_negative"),
        sa.CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
    )

    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_type", "orders", ["order_type"])
    op.create_index("ix_orders_created_at", "orders", ["created_at"])
    op.create_index("ix_orders_customer_name", "orders", ["customer_name"])
    op.create_index("ix_orders_customer_phone", "orders", ["customer_phone"])
    op.create_index("ix_orders_customer_email", "orders", ["customer_email"])

    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
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
        sa.Column("order_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("product_sku", sa.String(50), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "order_item_substitutions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
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
        sa.Column("order_item_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("original_item_id", sa.String(50), nullable=True),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("original_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("original_qty", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("price_difference", sa.Numeric(12, 2), nullable=True),
        sa.Column("customer_notified", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("substitute_item_id", sa.String(50), nullable=True),
        sa.Column("substitute_name", sa.String(200), nullable=False),
        sa.Column("substitute_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False),
        sa.ForeignKeyConstraint(["order_item_id"], ["order_items.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("order_item_id", name="uq_order_item_substitutions_item"),
    )

    op.create_table(
        "order_status_history",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
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
        sa.Column("order_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("changed_by", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"])
    op.create_index("ix_order_status_history_status", "order_status_history", ["status"])

    op.create_table(
        "order_contact_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
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
        sa.Column("order_id", postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("template_id", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_order_contact_attempts_order_id", "order_contact_attempts", ["order_id"])


def downgrade() -> None:
    """Drop order management tables."""
    op.drop_index("ix_order_contact_attempts_order_id", table_name="order_contact_attempts")
    op.drop_table("order_contact_attempts")

    op.drop_index("ix_order_status_history_status", table_name="order_status_history")
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")

    op.drop_table("order_item_substitutions")
    op.drop_index("ix_order_items_order_id", table_name="order_items")
    op.drop_table("order_items")

    op.drop_index("ix_orders_customer_email", table_name="orders")
    op.drop_index("ix_orders_customer_phone", table_name="orders")
    op.drop_index("ix_orders_customer_name", table_name="orders")
    op.drop_index("ix_orders_created_at", table_name="orders")
    op.drop_index("ix_orders_type", table_name="orders")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_table("orders")
