"""
Notifications Models
--------------------
Database models for staff notifications and read state.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models import BaseModel


class NotificationType(StrEnum):
    ORDER = "order"
    STOCK = "stock"
    ALERT = "alert"
    SUCCESS = "success"


class Notification(BaseModel):
    __tablename__ = "notifications"

    __table_args__ = (
        Index("ix_notifications_created_at", "created_at"),
        Index("ix_notifications_type", "type"),
        Index("ix_notifications_tenant_id", "tenant_id"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_href: Mapped[str | None] = mapped_column(String(500), nullable=True)


class NotificationRead(BaseModel):
    __tablename__ = "notification_reads"

    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_reads_notification_user"),
        Index("ix_notification_reads_user", "user_id"),
        Index("ix_notification_reads_notification", "notification_id"),
    )

    notification_id: Mapped[str] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
