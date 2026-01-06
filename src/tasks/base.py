"""
Base Task Classes
-----------------
Foundation for all background tasks with:
- Structured logging
- Retry policies with exponential backoff
- Idempotency support via task locks
- Correlation ID propagation
- Execution timing and metrics

Design Principles:
1. Every task logs its lifecycle (start, success, failure, retry)
2. Retries use exponential backoff to avoid thundering herd
3. Task locks prevent duplicate execution of the same logical task
4. All tasks can be ported to other backends (RQ, async, etc.)
"""

import functools
import hashlib
from abc import abstractmethod
from datetime import UTC, datetime
from typing import Any, ParamSpec, TypeVar

from celery import Task
from celery.exceptions import MaxRetriesExceededError, Reject
from redis import Redis

from src.core.config import get_settings
from src.core.logging import get_correlation_id, get_logger, set_correlation_id
from src.tasks.celery_app import celery_app

settings = get_settings()
logger = get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# ═══════════════════════════════════════════════════════════════════════════
# TASK LOCK (Idempotency)
# ═══════════════════════════════════════════════════════════════════════════


class TaskLock:
    """
    Distributed lock using Redis for task idempotency.
    
    Prevents duplicate task execution when:
    - Same task is scheduled multiple times
    - Worker restarts and reprocesses tasks
    - Multiple beat schedulers run simultaneously
    
    Usage:
        with TaskLock("check_low_stock", timeout=600) as acquired:
            if acquired:
                # Execute task
            else:
                # Skip - already running
    """
    
    def __init__(
        self,
        lock_name: str,
        timeout: int = 600,
        redis_client: Redis | None = None,
    ):
        self.lock_name = f"task_lock:{lock_name}"
        self.timeout = timeout
        self._redis: Redis | None = redis_client
        self._acquired = False
    
    @property
    def redis(self) -> Redis:
        """Lazy Redis connection."""
        if self._redis is None:
            self._redis = Redis.from_url(str(settings.redis_url))
        return self._redis
    
    def acquire(self) -> bool:
        """
        Attempt to acquire the lock.
        
        Returns True if lock was acquired, False if already held.
        """
        # SET NX (only if not exists) with expiration
        self._acquired = bool(
            self.redis.set(
                self.lock_name,
                datetime.now(UTC).isoformat(),
                nx=True,
                ex=self.timeout,
            )
        )
        return self._acquired
    
    def release(self) -> None:
        """Release the lock if we hold it."""
        if self._acquired:
            self.redis.delete(self.lock_name)
            self._acquired = False
    
    def extend(self, additional_time: int = 300) -> bool:
        """Extend lock timeout if task is still running."""
        if self._acquired:
            return bool(self.redis.expire(self.lock_name, additional_time))
        return False
    
    def __enter__(self) -> bool:
        return self.acquire()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def generate_lock_key(*args: Any, **kwargs: Any) -> str:
    """
    Generate a deterministic lock key from task arguments.
    
    This allows idempotency checks based on task parameters,
    not just task name.
    """
    key_data = f"{args}:{sorted(kwargs.items())}"
    return hashlib.md5(key_data.encode()).hexdigest()[:16]


# ═══════════════════════════════════════════════════════════════════════════
# BASE TASK CLASS
# ═══════════════════════════════════════════════════════════════════════════


class BaseTask(Task):
    """
    Enhanced Celery task with operational best practices.
    
    Features:
    - Automatic structured logging
    - Exponential backoff on retry
    - Correlation ID propagation
    - Execution timing
    - Error categorization
    
    Subclass this for all production tasks.
    """
    
    # Retry configuration
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # Max 10 minutes between retries
    retry_jitter = True  # Add randomness to prevent thundering herd
    max_retries = 3
    
    # Acknowledgment settings
    acks_late = True  # Ack after task completes (safer)
    reject_on_worker_lost = True  # Requeue if worker dies
    
    # Don't track results by default (saves Redis memory)
    ignore_result = True
    
    # Rate limiting (tasks per minute per worker)
    rate_limit = None
    
    def __init__(self) -> None:
        super().__init__()
        self._start_time: datetime | None = None
    
    @property
    def task_logger(self):
        """Get logger bound to task name."""
        return get_logger(f"task.{self.name}")
    
    def before_start(
        self,
        task_id: str,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Called just before task execution."""
        # Set correlation ID for this task
        correlation_id = kwargs.pop("correlation_id", None) or get_correlation_id()
        set_correlation_id(correlation_id)
        
        self._start_time = datetime.now(UTC)
        
        self.task_logger.info(
            "Task started",
            task_id=task_id,
            task_name=self.name,
            args=args,
            retry_count=self.request.retries,
        )
    
    def on_success(
        self,
        retval: Any,
        task_id: str,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Called when task completes successfully."""
        duration = self._calculate_duration()
        
        self.task_logger.info(
            "Task completed successfully",
            task_id=task_id,
            task_name=self.name,
            duration_seconds=duration,
            result_summary=self._summarize_result(retval),
        )
    
    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called when task fails after all retries."""
        duration = self._calculate_duration()
        
        self.task_logger.error(
            "Task failed permanently",
            task_id=task_id,
            task_name=self.name,
            duration_seconds=duration,
            error_type=type(exc).__name__,
            error_message=str(exc),
            retries_attempted=self.request.retries,
        )
    
    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: Any,
    ) -> None:
        """Called when task is retrying."""
        self.task_logger.warning(
            "Task retrying",
            task_id=task_id,
            task_name=self.name,
            retry_count=self.request.retries + 1,
            max_retries=self.max_retries,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    
    def _calculate_duration(self) -> float | None:
        """Calculate task duration in seconds."""
        if self._start_time:
            return (datetime.now(UTC) - self._start_time).total_seconds()
        return None
    
    def _summarize_result(self, retval: Any) -> str:
        """Create a brief summary of task result for logging."""
        if retval is None:
            return "None"
        if isinstance(retval, dict):
            return f"dict({len(retval)} keys)"
        if isinstance(retval, (list, tuple)):
            return f"{type(retval).__name__}({len(retval)} items)"
        return str(retval)[:100]


# ═══════════════════════════════════════════════════════════════════════════
# SCHEDULED TASK BASE
# ═══════════════════════════════════════════════════════════════════════════


class ScheduledTask(BaseTask):
    """
    Base class for scheduled/periodic tasks.
    
    Adds:
    - Distributed locking (only one instance runs)
    - Skip if already running
    - Lock timeout management
    """
    
    # Override in subclass
    lock_timeout: int = 600  # 10 minutes default
    
    @property
    @abstractmethod
    def lock_name(self) -> str:
        """Unique name for the task lock."""
        ...
    
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        """Execute with distributed lock."""
        with TaskLock(self.lock_name, timeout=self.lock_timeout) as acquired:
            if not acquired:
                self.task_logger.info(
                    "Task skipped - already running",
                    task_name=self.name,
                    lock_name=self.lock_name,
                )
                return {"status": "skipped", "reason": "already_running"}
            
            return self.run(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════════════════
# TASK DECORATOR WITH DEFAULTS
# ═══════════════════════════════════════════════════════════════════════════


def task_with_retry(
    *,
    max_retries: int = 3,
    retry_backoff: bool = True,
    retry_backoff_max: int = 600,
    rate_limit: str | None = None,
    ignore_result: bool = True,
):
    """
    Decorator for creating tasks with sensible retry defaults.
    
    Usage:
        @task_with_retry(max_retries=5, rate_limit="10/m")
        def my_task(arg1, arg2):
            ...
    """
    def decorator(func):
        @celery_app.task(
            base=BaseTask,
            bind=True,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            retry_backoff_max=retry_backoff_max,
            rate_limit=rate_limit,
            ignore_result=ignore_result,
        )
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            return func(*args, **kwargs)
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC DATABASE SESSION FOR TASKS
# ═══════════════════════════════════════════════════════════════════════════


async def get_task_session():
    """
    Get a database session for use in Celery tasks.
    
    Since Celery workers are sync, we need to run async code
    in an event loop. Use this with asyncio.run().
    """
    from src.core.database import async_session_factory
    
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def run_async(coro):
    """
    Run an async coroutine in a sync context.
    
    For Celery tasks that need to call async code.
    """
    import asyncio
    
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
