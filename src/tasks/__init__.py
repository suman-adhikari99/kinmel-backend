"""
Background Tasks Module
=======================
Celery-based background task processing for Kinmel Inventory System.

Components:
-----------
- celery_app: Main Celery application instance
- base: Base task classes with retry, logging, idempotency
- notifications: Multi-channel alert dispatcher
- inventory_tasks: Low stock, expiry checks
- report_tasks: Daily summaries, movement reports

Quick Start:
-----------
# Start worker
celery -A src.tasks.celery_app worker --loglevel=info

# Start beat scheduler
celery -A src.tasks.celery_app beat --loglevel=info

# Combined (dev only)
celery -A src.tasks.celery_app worker --beat --loglevel=info

Manual Task Triggers:
--------------------
>>> from src.tasks import trigger_low_stock_check, trigger_daily_summary
>>> result = trigger_low_stock_check()
>>> result.get()  # Wait for result (if task returns result)

Scheduled Tasks:
---------------
| Task                    | Schedule           | Purpose                    |
|-------------------------|--------------------|----------------------------|
| check_critical_stock    | Every 5 min        | Out of stock alerts        |
| check_low_stock_levels  | Every 15 min       | Low stock alerts           |
| check_expiring_products | Daily 6 AM         | Expiry warnings            |
| generate_daily_summary  | Daily midnight     | Health score report        |
| send_inventory_digest   | Daily 8 AM         | Manager digest email       |
| generate_movement_report| Weekly Monday 1 AM | Movement audit report      |
| reconcile_batch_totals  | Weekly Sunday 2 AM | Data integrity check       |
"""

# Celery app instance (import this for workers)
from src.tasks.celery_app import celery_app

# Base task classes
from src.tasks.base import (
    BaseTask,
    ScheduledTask,
    TaskLock,
    run_async,
    task_with_retry,
)

# Notification system
from src.tasks.notifications import (
    Alert,
    AlertCategory,
    AlertSeverity,
    NotificationDispatcher,
    get_dispatcher,
    send_alert,
    send_expiry_alert,
    send_low_stock_alert,
)

# Convenience triggers for manual task execution
from src.tasks.celery_app import (
    trigger_daily_summary,
    trigger_expiry_check,
    trigger_inventory_digest,
    trigger_low_stock_check,
)

__all__ = [
    # Celery
    "celery_app",
    
    # Base classes
    "BaseTask",
    "ScheduledTask",
    "TaskLock",
    "run_async",
    "task_with_retry",
    
    # Notifications
    "Alert",
    "AlertCategory",
    "AlertSeverity",
    "NotificationDispatcher",
    "get_dispatcher",
    "send_alert",
    "send_expiry_alert",
    "send_low_stock_alert",
    
    # Triggers
    "trigger_low_stock_check",
    "trigger_expiry_check",
    "trigger_daily_summary",
    "trigger_inventory_digest",
]
