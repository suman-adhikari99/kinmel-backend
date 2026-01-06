from __future__ import annotations

"""
Order Domain Models
-------------------
Core entities for order tracking, fulfillment, and substitutions.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import BaseModel


# ═══════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════

class OrderType(StrEnum):
    """Order fulfillment type."""

    PICKUP = "pickup"
    DELIVERY = "delivery"


class OrderStatus(StrEnum):
    """Lifecycle status for an order."""

    NEW = "new"
    PREPARING = "preparing"
    READY = "ready"
    OUT_FOR_DELIVERY = "out_for_delivery"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SubstitutionStatus(StrEnum):
    """Status for an item substitution request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ContactChannel(StrEnum):
    """Customer contact channel."""

    CALL = "call"
    SMS = "sms"
    EMAIL = "email"
    WHATSAPP = "whatsapp"


class OrderExportStatus(StrEnum):
    """Status for export jobs."""

    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


# ═══════════════════════════════════════════════════════════════════
# ORDER MODEL
# ═══════════════════════════════════════════════════════════════════

class Order(BaseModel):
    """
    Customer order with fulfillment data.
    """

    __tablename__ = "orders"

    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="ck_orders_subtotal_non_negative"),
        CheckConstraint("gst >= 0", name="ck_orders_gst_non_negative"),
        CheckConstraint("delivery_fee >= 0", name="ck_orders_delivery_fee_non_negative"),
        CheckConstraint("total >= 0", name="ck_orders_total_non_negative"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_type", "order_type"),
        Index("ix_orders_created_at", "created_at"),
        Index("ix_orders_customer_name", "customer_name"),
        Index("ix_orders_customer_phone", "customer_phone"),
        Index("ix_orders_customer_email", "customer_email"),
    )

    order_type: Mapped[OrderType] = mapped_column(
        String(20),
        nullable=False,
        doc="Order type: pickup or delivery",
    )

    status: Mapped[OrderStatus] = mapped_column(
        String(30),
        nullable=False,
        default=OrderStatus.NEW,
        doc="Order status",
    )

    time_slot: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Pickup/delivery time slot",
    )

    customer_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Customer full name",
    )

    customer_phone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Customer phone number",
    )

    customer_email: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        doc="Customer email address",
    )

    delivery_address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Delivery address",
    )

    delivery_suburb: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Delivery suburb",
    )

    subtotal: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="Order subtotal",
    )

    gst: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="GST/tax amount",
    )

    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="Delivery fee",
    )

    total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="Order total",
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Internal notes",
    )

    has_substitutions: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Whether any substitutions exist",
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when order was delivered/completed",
    )

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="desc(OrderItem.created_at)",
        lazy="selectin",
    )

    status_history: Mapped[list["OrderStatusHistory"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    contact_attempts: Mapped[list["OrderContactAttempt"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ═══════════════════════════════════════════════════════════════════
# ORDER ITEM MODEL
# ═══════════════════════════════════════════════════════════════════

class OrderItem(BaseModel):
    """Line item within an order."""

    __tablename__ = "order_items"

    __table_args__ = (
        Index("ix_order_items_order_id", "order_id"),
    )

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    product_sku: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="SKU or external product identifier",
    )

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Item name at time of order",
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="Ordered quantity",
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        doc="Unit price at time of order",
    )

    checked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Pick/pack checklist flag",
    )

    order: Mapped["Order"] = relationship(
        back_populates="items",
        lazy="selectin",
    )

    substitution: Mapped[Optional["OrderItemSubstitution"]] = relationship(
        back_populates="order_item",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )


# ═══════════════════════════════════════════════════════════════════
# ITEM SUBSTITUTION MODEL
# ═══════════════════════════════════════════════════════════════════

class OrderItemSubstitution(BaseModel):
    """Substitution details for an order item."""

    __tablename__ = "order_item_substitutions"

    __table_args__ = (
        UniqueConstraint("order_item_id", name="uq_order_item_substitutions_item"),
    )

    order_item_id: Mapped[str] = mapped_column(
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
    )

    original_item_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    original_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    original_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    original_qty: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    price_difference: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        doc="Price difference between original and substitute",
    )

    customer_notified: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Whether customer was notified of substitution",
    )

    status: Mapped[SubstitutionStatus] = mapped_column(
        String(20),
        nullable=False,
        default=SubstitutionStatus.PENDING,
    )

    substitute_item_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    substitute_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    substitute_price: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    quantity: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    order_item: Mapped["OrderItem"] = relationship(
        back_populates="substitution",
        lazy="selectin",
    )


# ═══════════════════════════════════════════════════════════════════
# STATUS HISTORY MODEL
# ═══════════════════════════════════════════════════════════════════

class OrderStatusHistory(BaseModel):
    """Audit trail of order status changes."""

    __tablename__ = "order_status_history"

    __table_args__ = (
        Index("ix_order_status_history_order_id", "order_id"),
        Index("ix_order_status_history_status", "status"),
    )

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[OrderStatus] = mapped_column(
        String(30),
        nullable=False,
    )

    changed_by: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        doc="User ID who changed the status",
    )

    order: Mapped["Order"] = relationship(
        back_populates="status_history",
        lazy="selectin",
    )


# ═══════════════════════════════════════════════════════════════════
# CONTACT ATTEMPTS MODEL
# ═══════════════════════════════════════════════════════════════════

class OrderContactAttempt(BaseModel):
    """Log of contact attempts for an order."""

    __tablename__ = "order_contact_attempts"

    __table_args__ = (
        Index("ix_order_contact_attempts_order_id", "order_id"),
    )

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    channel: Mapped[ContactChannel] = mapped_column(
        String(20),
        nullable=False,
    )

    template_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    order: Mapped["Order"] = relationship(
        back_populates="contact_attempts",
        lazy="selectin",
    )


# ═══════════════════════════════════════════════════════════════════
# ORDER EXPORT JOB MODEL
# ═══════════════════════════════════════════════════════════════════

class OrderExportJob(BaseModel):
    """Background export job metadata."""

    __tablename__ = "order_export_jobs"

    __table_args__ = (
        Index("ix_order_export_jobs_status", "status"),
        Index("ix_order_export_jobs_requested_by", "requested_by"),
    )

    requested_by: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        doc="User ID who requested the export",
    )

    destination_email: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="Email recipient for the export",
    )

    status: Mapped[OrderExportStatus] = mapped_column(
        String(20),
        nullable=False,
        default=OrderExportStatus.PENDING,
    )

    filters_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        doc="JSON string with export filters",
    )

    file_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Optional download URL for export file",
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Failure reason if export fails",
    )
