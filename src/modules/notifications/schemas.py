"""
Notifications Schemas
---------------------
Pydantic models for notification endpoints.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base model with strict configuration."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )


NotificationType = Literal["order", "stock", "alert", "success"]
FilterType = Literal["all", "unread"]
SortDir = Literal["asc", "desc"]


class NotificationSource(StrictModel):
    label: str | None = None
    href: str | None = None


class NotificationSeenBy(StrictModel):
    id: str
    name: str


class NotificationItem(StrictModel):
    id: str
    type: NotificationType
    title: str
    message: str
    created_at: datetime
    read: bool
    source: NotificationSource | None = None
    seen_by: list[NotificationSeenBy]


class NotificationsListResponse(StrictModel):
    items: list[NotificationItem]
    total: int
    unread_count: int
    retention_days: int


class NotificationReadResponse(StrictModel):
    id: str
    read: bool
    read_at: datetime


class NotificationsReadAllResponse(StrictModel):
    success: bool
    updated_count: int


class NotificationDeleteResponse(StrictModel):
    success: bool
