"""
Celery Configuration
--------------------
Background task processing for operations that:
- Take too long for a request/response cycle
- Need retry logic
- Should run on a schedule
- Can fail without breaking the user experience

Examples:
- Generate large reports
- Send low-stock alerts
- Process bulk imports
- Clean up expired products

Running Celery:
--------------
# Start worker (processes tasks)
celery -A src.tasks.celery_app worker --loglevel=info

# Start beat scheduler (schedules periodic tasks)
celery -A src.tasks.celery_app beat --loglevel=info

# Combined (development only)
celery -A src.tasks.celery_app worker --beat --loglevel=info

# With concurrency control
celery -A src.tasks.celery_app worker -c 4 --loglevel=info
"""

from celery import Celery
from celery.schedules import crontab

from src.core.config import get_settings

settings = get_settings()

# ─────────────────────────────────────────────────────────────────
# Celery App Configuration
# ─────────────────────────────────────────────────────────────────

celery_app = Celery(
    "kinmel",
    broker=str(settings.redis_url),
    backend=str(settings.redis_url),
    # Auto-discover tasks in these modules
    include=[
        "src.tasks.inventory_tasks",
        "src.tasks.report_tasks",
        "src.tasks.order_tasks",
        "src.tasks.email_tasks",
        "src.tasks.notification_tasks",
    ],
)

celery_app.conf.update(
    # ─────────────────────────────────────────────────────────────
    # Broker Connection
    # ─────────────────────────────────────────────────────────────
    broker_connection_retry_on_startup=True,
    
    # ─────────────────────────────────────────────────────────────
    # Serialization
    # ─────────────────────────────────────────────────────────────
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # ─────────────────────────────────────────────────────────────
    # Timezone
    # ─────────────────────────────────────────────────────────────
    timezone="UTC",
    enable_utc=True,
    
    # ─────────────────────────────────────────────────────────────
    # Reliability Settings
    # ─────────────────────────────────────────────────────────────
    # Acknowledge AFTER task completes (safer - prevents task loss)
    task_acks_late=True,
    
    # Re-queue task if worker dies mid-execution
    task_reject_on_worker_lost=True,
    
    # Hard time limit (kill task if exceeds)
    task_time_limit=3600,  # 1 hour
    
    # Soft time limit (raise exception, allows cleanup)
    task_soft_time_limit=3300,  # 55 minutes
    
    # ─────────────────────────────────────────────────────────────
    # Retry Settings (defaults, can override per task)
    # ─────────────────────────────────────────────────────────────
    task_default_retry_delay=60,  # 1 minute initial delay
    task_max_retries=3,
    
    # ─────────────────────────────────────────────────────────────
    # Worker Settings
    # ─────────────────────────────────────────────────────────────
    # Fetch one task at a time (fair scheduling, prevents starvation)
    worker_prefetch_multiplier=1,
    
    # Number of concurrent worker processes
    worker_concurrency=4,
    
    # Max tasks before worker restart (prevents memory leaks)
    worker_max_tasks_per_child=1000,
    
    # ─────────────────────────────────────────────────────────────
    # Result Backend Settings
    # ─────────────────────────────────────────────────────────────
    # Results expire after 24 hours
    result_expires=86400,
    
    # Don't store successful results by default (saves memory)
    task_ignore_result=True,
    
    # ─────────────────────────────────────────────────────────────
    # Task Routing (optional - for different queues)
    # ─────────────────────────────────────────────────────────────
    task_routes={
        # High priority: alert checks
        "src.tasks.inventory_tasks.check_critical_stock": {"queue": "high_priority"},
        "src.tasks.inventory_tasks.check_low_stock_levels": {"queue": "high_priority"},
        
        # Default: normal tasks
        "src.tasks.inventory_tasks.*": {"queue": "default"},
        
        # Low priority: reports (can wait)
        "src.tasks.report_tasks.*": {"queue": "low_priority"},
    },
    
    # Default queue if not specified
    task_default_queue="default",
    
    # ─────────────────────────────────────────────────────────────
    # Beat Schedule (Periodic Tasks)
    # ─────────────────────────────────────────────────────────────
    beat_schedule={
        # ───────────────────────────────────────────────────────
        # CRITICAL: Out of stock check (every 5 minutes)
        # ───────────────────────────────────────────────────────
        "check-critical-stock": {
            "task": "src.tasks.inventory_tasks.check_critical_stock",
            "schedule": 300.0,  # 5 minutes
            "options": {"queue": "high_priority"},
        },
        
        # ───────────────────────────────────────────────────────
        # LOW STOCK: Full check (every 15 minutes)
        # ───────────────────────────────────────────────────────
        "check-low-stock-levels": {
            "task": "src.tasks.inventory_tasks.check_low_stock_levels",
            "schedule": 900.0,  # 15 minutes
            "options": {"queue": "high_priority"},
        },
        
        # ───────────────────────────────────────────────────────
        # EXPIRY: Daily check at 6:00 AM UTC
        # ───────────────────────────────────────────────────────
        "check-expiring-products": {
            "task": "src.tasks.inventory_tasks.check_expiring_products",
            "schedule": crontab(hour=6, minute=0),
            "kwargs": {"days_ahead": 7},
        },
        
        # ───────────────────────────────────────────────────────
        # DAILY SUMMARY: Midnight UTC
        # ───────────────────────────────────────────────────────
        "daily-summary-report": {
            "task": "src.tasks.report_tasks.generate_daily_summary",
            "schedule": crontab(hour=0, minute=5),
            "options": {"queue": "low_priority"},
        },
        
        # ───────────────────────────────────────────────────────
        # MORNING DIGEST: 8:00 AM UTC (adjust for your timezone)
        # ───────────────────────────────────────────────────────
        "morning-inventory-digest": {
            "task": "src.tasks.report_tasks.send_inventory_digest",
            "schedule": crontab(hour=8, minute=0),
            "options": {"queue": "low_priority"},
        },
        
        # ───────────────────────────────────────────────────────
        # WEEKLY MOVEMENT REPORT: Monday at 1:00 AM UTC
        # ───────────────────────────────────────────────────────
        "weekly-movement-report": {
            "task": "src.tasks.report_tasks.generate_movement_report",
            "schedule": crontab(hour=1, minute=0, day_of_week="monday"),
            "kwargs": {"days": 7},
            "options": {"queue": "low_priority"},
        },
        
        # ───────────────────────────────────────────────────────
        # DATA INTEGRITY: Weekly reconciliation (Sunday 2 AM)
        # ───────────────────────────────────────────────────────
        "weekly-batch-reconciliation": {
            "task": "src.tasks.inventory_tasks.reconcile_batch_totals",
            "schedule": crontab(hour=2, minute=0, day_of_week="sunday"),
        },

        # ───────────────────────────────────────────────────────
        # NOTIFICATIONS RETENTION: Daily at 2:30 AM UTC
        # ───────────────────────────────────────────────────────
        "cleanup-notifications": {
            "task": "src.tasks.notification_tasks.cleanup_notifications",
            "schedule": crontab(hour=2, minute=30),
        },
    },
    
    # ─────────────────────────────────────────────────────────────
    # Beat Scheduler Settings
    # ─────────────────────────────────────────────────────────────
    # Store beat schedule in Redis (allows multiple beat instances)
    # Uncomment if using celery-redbeat:
    # beat_scheduler="redbeat.RedBeatScheduler",
    # redbeat_redis_url=str(settings.redis_url),
)


# ─────────────────────────────────────────────────────────────────
# Task Autodiscovery
# ─────────────────────────────────────────────────────────────────
# Explicitly discover tasks (include= in Celery() is preferred)
# celery_app.autodiscover_tasks(["src.tasks"])


# ─────────────────────────────────────────────────────────────────
# Celery Signals (Hooks)
# ─────────────────────────────────────────────────────────────────

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    """
    Additional setup after Celery is configured.
    
    This hook runs after the app is configured but before
    workers start processing tasks.
    """
    from src.core.logging import configure_logging
    configure_logging()


# ─────────────────────────────────────────────────────────────────
# Manual Task Triggers (for testing/debugging)
# ─────────────────────────────────────────────────────────────────

def trigger_low_stock_check(location_id: str | None = None):
    """Manually trigger low stock check."""
    from src.tasks.inventory_tasks import check_low_stock_levels
    return check_low_stock_levels.delay(location_id=location_id)


def trigger_expiry_check(days_ahead: int = 7, location_id: str | None = None):
    """Manually trigger expiry check."""
    from src.tasks.inventory_tasks import check_expiring_products
    return check_expiring_products.delay(days_ahead=days_ahead, location_id=location_id)


def trigger_daily_summary():
    """Manually trigger daily summary."""
    from src.tasks.report_tasks import generate_daily_summary
    return generate_daily_summary.delay()


def trigger_inventory_digest():
    """Manually trigger inventory digest."""
    from src.tasks.report_tasks import send_inventory_digest
    return send_inventory_digest.delay()
