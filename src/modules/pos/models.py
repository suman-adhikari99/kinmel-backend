"""
POS Domain Models
-----------------
Checkout reservation and audit entities for point-of-sale flows.
"""

from datetime import datetime
from enum import StrEnum
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import BaseModel

class PosSaleStatus(StrEnum):
    RESERVED = "reserved"
    COMMITTED = "committed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class PosSale(BaseModel):
    __tablename__ = "pos_sales"

    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_pos_sales_idempotency_key"),
        Index("ix_pos_sales_status", "status"),
        Index("ix_pos_sales_reserved_until", "reserved_until"),
    )

    location_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[PosSaleStatus] = mapped_column(
        String(20),
        nullable=False,
        default=PosSaleStatus.RESERVED,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    reserved_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_by: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    lines: Mapped[list["PosSaleLine"]] = relationship(
        back_populates="sale",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PosSaleLine(BaseModel):
    __tablename__ = "pos_sale_lines"

    __table_args__ = (
        Index("ix_pos_sale_lines_sale", "sale_id"),
    )

    sale_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("pos_sales.id", ondelete="CASCADE"),
        nullable=False,
    )
    barcode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    qty: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    unit_price_at_sale: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )
    tax_rate_at_sale: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )
    name_snapshot: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    sale: Mapped["PosSale"] = relationship(
        back_populates="lines",
    )
