"""
Revenue Domain Models
---------------------
Models for payments, payouts, adjustments, and business profile.
"""

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models import BaseModel


class PaymentMethod(StrEnum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    CASH = "cash"
    DIGITAL_WALLET = "digital_wallet"
    BANK_TRANSFER = "bank_transfer"
    OTHER = "other"


class PaymentStatus(StrEnum):
    COMPLETED = "completed"
    REFUNDED = "refunded"
    FAILED = "failed"


class PayoutStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"


class AdjustmentType(StrEnum):
    PLATFORM_FEE = "platform_fee"
    REFUND = "refund"
    DISPUTE = "dispute"


class RevenuePayment(BaseModel):
    """Payment record tied to an order."""

    __tablename__ = "revenue_payments"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_revenue_payments_amount_non_negative"),
        Index("ix_revenue_payments_order_id", "order_id"),
        Index("ix_revenue_payments_status", "status"),
        Index("ix_revenue_payments_method", "method"),
    )

    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    method: Mapped[PaymentMethod] = mapped_column(
        String(30),
        nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PaymentStatus.COMPLETED,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )


class RevenuePayout(BaseModel):
    """Payout record from processor."""

    __tablename__ = "revenue_payouts"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_revenue_payouts_amount_non_negative"),
        Index("ix_revenue_payouts_status", "status"),
        Index("ix_revenue_payouts_payout_at", "payout_at"),
    )

    payout_at: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        doc="ISO timestamp string for payout scheduling",
    )

    status: Mapped[PayoutStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PayoutStatus.PENDING,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )


class RevenueAdjustment(BaseModel):
    """Adjustments like platform fees, refunds, disputes."""

    __tablename__ = "revenue_adjustments"

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_revenue_adjustments_amount_non_negative"),
        Index("ix_revenue_adjustments_type", "adjustment_type"),
    )

    adjustment_type: Mapped[AdjustmentType] = mapped_column(
        String(30),
        nullable=False,
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class BusinessProfile(BaseModel):
    """Business profile and compliance information."""

    __tablename__ = "business_profile"

    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    abn: Mapped[str] = mapped_column(String(30), nullable=False)
    gst_registered: Mapped[bool] = mapped_column(default=True, nullable=False)
    gst_rate: Mapped[str] = mapped_column(String(10), nullable=False)
    store_address: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(50), nullable=False)
    bank_masked: Mapped[str] = mapped_column(String(50), nullable=False)
    payout_frequency: Mapped[str] = mapped_column(String(30), nullable=False, default="Daily")
    processor: Mapped[str] = mapped_column(String(50), nullable=False, default="Stripe")
