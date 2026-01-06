"""
Notification Background Tasks
-----------------------------
Retention cleanup for notifications.
"""

from typing import Any

from src.core.logging import get_logger
from src.tasks.base import BaseTask, run_async
from src.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.notification_tasks.cleanup_notifications",
)
def cleanup_notifications(self) -> dict[str, Any]:
    """Delete notifications older than retention window."""
    return run_async(_cleanup_notifications_async())


async def _cleanup_notifications_async() -> dict[str, Any]:
    from src.core.database import async_session_factory
    from src.modules.notifications.repository import RETENTION_DAYS, notifications_repository

    async with async_session_factory() as session:
        deleted_count = await notifications_repository.cleanup_retention(
            session,
            retention_days=RETENTION_DAYS,
        )
        await session.commit()

    logger.info("Notifications cleanup completed", deleted=deleted_count)
    return {"deleted": deleted_count}
