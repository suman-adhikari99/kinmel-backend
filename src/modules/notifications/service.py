"""
Notifications Service
---------------------
Real-time delivery helpers and high-level operations.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

try:
    from redis.asyncio import Redis
except ImportError:  # pragma: no cover - fallback for minimal envs
    Redis = None  # type: ignore[assignment]

from src.core.config import get_settings
from src.modules.notifications.repository import notifications_repository


@dataclass
class NotificationEvent:
    event: str
    data: dict[str, Any]


class NotificationEventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue[NotificationEvent]] = []

    def subscribe(self) -> asyncio.Queue[NotificationEvent]:
        queue: asyncio.Queue[NotificationEvent] = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[NotificationEvent]) -> None:
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    async def publish(self, event: NotificationEvent) -> None:
        for queue in list(self._subscribers):
            await queue.put(event)


event_bus = NotificationEventBus()
settings = get_settings()
_REDIS_CHANNEL = "notifications:events"


async def _publish_event(event: NotificationEvent) -> None:
    payload = json.dumps({"event": event.event, "data": event.data}, default=str)
    try:
        if Redis is None:
            raise RuntimeError("redis.asyncio not available")
        redis = Redis.from_url(str(settings.redis_url))
        await redis.publish(_REDIS_CHANNEL, payload)
        await redis.close()
    except Exception:
        await event_bus.publish(event)


def _format_sse(event: NotificationEvent) -> str:
    payload = json.dumps(event.data, default=str)
    return f"event: {event.event}\ndata: {payload}\n\n"


async def sse_stream() -> AsyncIterator[str]:
    try:
        if Redis is None:
            raise RuntimeError("redis.asyncio not available")
        redis = Redis.from_url(str(settings.redis_url))
        pubsub = redis.pubsub()
        await pubsub.subscribe(_REDIS_CHANNEL)
        try:
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=15.0,
                    )
                    if message and message.get("data"):
                        payload = json.loads(message["data"])
                        event = NotificationEvent(event=payload["event"], data=payload["data"])
                        yield _format_sse(event)
                    else:
                        yield ": keep-alive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            await pubsub.unsubscribe(_REDIS_CHANNEL)
            await pubsub.close()
            await redis.close()
    except Exception:
        queue = event_bus.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _format_sse(event)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                except asyncio.CancelledError:
                    break
        finally:
            event_bus.unsubscribe(queue)


class NotificationsService:
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
    ) -> dict:
        notification = await notifications_repository.create_notification(
            session,
            notif_type=notif_type,
            title=title,
            message=message,
            tenant_id=tenant_id,
            source_label=source_label,
            source_href=source_href,
        )
        await _publish_event(
            NotificationEvent(
                event="notification.created",
                data={
                    "id": notification.id,
                    "type": notification.type,
                    "title": notification.title,
                    "message": notification.message,
                    "created_at": notification.created_at,
                    "read": False,
                    "source": {
                        "label": notification.source_label,
                        "href": notification.source_href,
                    }
                    if notification.source_label or notification.source_href
                    else None,
                    "seen_by": [],
                },
            )
        )
        return {
            "id": notification.id,
            "type": notification.type,
            "title": notification.title,
            "message": notification.message,
            "created_at": notification.created_at,
        }

    async def publish_read(self, notification_id: str, read_at) -> None:
        await _publish_event(
            NotificationEvent(
                event="notification.read",
                data={
                    "id": notification_id,
                    "read": True,
                    "read_at": read_at,
                },
            )
        )

    async def publish_deleted(self, notification_id: str) -> None:
        await _publish_event(
            NotificationEvent(
                event="notification.deleted",
                data={"id": notification_id},
            )
        )


notifications_service = NotificationsService()
