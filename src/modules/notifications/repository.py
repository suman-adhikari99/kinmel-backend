"""
Notifications Repository
------------------------
Data access for notifications and read state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.modules.notifications.models import Notification, NotificationRead
from src.modules.users.models import User


RETENTION_DAYS = 30


class NotificationsRepository:
    async def list_notifications(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        limit: int,
        offset: int,
        filter_by: str,
        notif_type: str | None,
        since: datetime | None,
        sort_dir: str,
    ) -> tuple[list[dict], int, int]:
        read_alias = aliased(NotificationRead)
        base_filters = []
        if notif_type:
            base_filters.append(Notification.type == notif_type)
        if since:
            base_filters.append(Notification.created_at >= since)

        query = (
            select(Notification, read_alias.read_at)
            .outerjoin(
                read_alias,
                and_(
                    read_alias.notification_id == Notification.id,
                    read_alias.user_id == user_id,
                ),
            )
            .where(*base_filters)
        )
        if filter_by == "unread":
            query = query.where(read_alias.id.is_(None))

        order_col = Notification.created_at.asc() if sort_dir == "asc" else Notification.created_at.desc()
        query = query.order_by(order_col).offset(offset).limit(limit)

        result = await session.execute(query)
        rows = result.all()

        items = []
        notification_ids = []
        for notification, read_at in rows:
            notification_ids.append(notification.id)
            items.append(
                {
                    "id": notification.id,
                    "type": notification.type,
                    "title": notification.title,
                    "message": notification.message,
                    "created_at": notification.created_at,
                    "read": read_at is not None,
                    "source": {
                        "label": notification.source_label,
                        "href": notification.source_href,
                    }
                    if notification.source_label or notification.source_href
                    else None,
                    "seen_by": [],
                }
            )

        total_query = select(func.count()).select_from(Notification).where(*base_filters)
        total = await session.scalar(total_query) or 0

        unread_query = (
            select(func.count())
            .select_from(Notification)
            .outerjoin(
                read_alias,
                and_(
                    read_alias.notification_id == Notification.id,
                    read_alias.user_id == user_id,
                ),
            )
            .where(*base_filters)
            .where(read_alias.id.is_(None))
        )
        unread_count = await session.scalar(unread_query) or 0

        if notification_ids:
            seen_rows = await session.execute(
                select(
                    NotificationRead.notification_id,
                    User.id,
                    User.full_name,
                )
                .join(User, NotificationRead.user_id == User.id)
                .where(NotificationRead.notification_id.in_(notification_ids))
            )
            seen_map: dict[str, list[dict]] = {}
            for notification_id, user_id, full_name in seen_rows.all():
                seen_map.setdefault(notification_id, []).append(
                    {"id": user_id, "name": full_name}
                )
            for item in items:
                item["seen_by"] = seen_map.get(item["id"], [])

        return items, total, unread_count

    async def mark_read(
        self,
        session: AsyncSession,
        *,
        notification_id: str,
        user_id: str,
    ) -> datetime | None:
        exists = await session.scalar(
            select(Notification.id).where(Notification.id == notification_id)
        )
        if not exists:
            return None
        existing = await session.execute(
            select(NotificationRead).where(
                NotificationRead.notification_id == notification_id,
                NotificationRead.user_id == user_id,
            )
        )
        record = existing.scalar_one_or_none()
        now = datetime.now(UTC)
        if record:
            record.read_at = now
            return record.read_at
        session.add(
            NotificationRead(
                notification_id=notification_id,
                user_id=user_id,
                read_at=now,
            )
        )
        return now

    async def mark_all_read(
        self,
        session: AsyncSession,
        *,
        user_id: str,
    ) -> int:
        read_alias = aliased(NotificationRead)
        unread_query = (
            select(Notification.id)
            .outerjoin(
                read_alias,
                and_(
                    read_alias.notification_id == Notification.id,
                    read_alias.user_id == user_id,
                ),
            )
            .where(read_alias.id.is_(None))
        )
        result = await session.execute(unread_query)
        notification_ids = [row[0] for row in result.all()]
        now = datetime.now(UTC)
        for notification_id in notification_ids:
            session.add(
                NotificationRead(
                    notification_id=notification_id,
                    user_id=user_id,
                    read_at=now,
                )
            )
        return len(notification_ids)

    async def delete_notification(
        self,
        session: AsyncSession,
        *,
        notification_id: str,
    ) -> bool:
        result = await session.execute(
            delete(Notification).where(Notification.id == notification_id).returning(Notification.id)
        )
        deleted_id = result.scalar_one_or_none()
        return deleted_id is not None

    async def create_notification(
        self,
        session: AsyncSession,
        *,
        notif_type: str,
        title: str,
        message: str,
        tenant_id: str | None = None,
        source_label: str | None = None,
        source_href: str | None = None,
    ) -> Notification:
        notification = Notification(
            tenant_id=tenant_id,
            type=notif_type,
            title=title,
            message=message,
            source_label=source_label,
            source_href=source_href,
        )
        session.add(notification)
        await session.flush()
        return notification

    async def notification_exists(
        self,
        session: AsyncSession,
        *,
        title: str | None = None,
        source_href: str | None = None,
    ) -> bool:
        filters = []
        if title:
            filters.append(Notification.title == title)
        if source_href:
            filters.append(Notification.source_href == source_href)
        if not filters:
            return False
        exists = await session.scalar(select(Notification.id).where(*filters).limit(1))
        return exists is not None

    async def cleanup_retention(
        self,
        session: AsyncSession,
        *,
        retention_days: int = RETENTION_DAYS,
    ) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        result = await session.execute(
            delete(Notification).where(Notification.created_at < cutoff).returning(Notification.id)
        )
        deleted_ids = result.scalars().all()
        return len(deleted_ids)


notifications_repository = NotificationsRepository()
