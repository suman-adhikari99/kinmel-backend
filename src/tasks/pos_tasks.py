"""
POS Background Tasks
--------------------
Scheduled tasks for POS checkout maintenance.
"""

from datetime import UTC, datetime
from typing import Any

from src.core.logging import get_logger
from src.tasks.base import BaseTask, TaskLock, run_async
from src.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.pos_tasks.expire_pos_reservations",
    max_retries=3,
    default_retry_delay=60,
)
def expire_pos_reservations(self) -> dict[str, Any]:
    lock_name = "expire-pos-reservations"
    with TaskLock(lock_name, timeout=120) as acquired:
        if not acquired:
            logger.info("POS expiry skipped - already running")
            return {"status": "skipped", "reason": "already_running"}

        return run_async(_expire_pos_reservations_async())


async def _expire_pos_reservations_async() -> dict[str, Any]:
    from src.core.database import async_session_factory
    from src.modules.pos.service import pos_service

    now = datetime.now(UTC)
    async with async_session_factory() as session:
        result = await pos_service.expire_reserved_sales(session, now)
    return result
