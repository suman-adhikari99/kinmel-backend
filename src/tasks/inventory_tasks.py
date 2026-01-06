"""
Inventory Background Tasks
--------------------------
Scheduled tasks for inventory monitoring and alerting.

Tasks:
1. check_low_stock_levels - Detect items below reorder point
2. check_expiring_products - Detect batches near expiry
3. check_out_of_stock - Detect zero-stock items (critical)
4. sync_inventory_totals - Recalculate denormalized totals (if any)

Scheduling:
- Low stock: Every 15 minutes
- Expiry check: Daily at 6 AM
- Out of stock: Every 5 minutes (critical)

Idempotency:
- Each task uses distributed locks to prevent overlap
- Alerts are deduplicated to prevent notification spam
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.core.config import get_settings
from src.core.logging import get_logger
from src.tasks.base import BaseTask, TaskLock, run_async
from src.tasks.celery_app import celery_app
from src.tasks.notifications import (
    Alert,
    AlertCategory,
    AlertSeverity,
    get_dispatcher,
    send_expiry_alert,
    send_low_stock_alert,
)

settings = get_settings()
logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# LOW STOCK CHECK
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.inventory_tasks.check_low_stock_levels",
    max_retries=3,
    default_retry_delay=60,
)
def check_low_stock_levels(self, location_id: str | None = None) -> dict[str, Any]:
    """
    Check for items at or below reorder point.
    
    This task:
    1. Queries all inventory items where physical_stock <= reorder_point
    2. Groups by severity (out of stock vs low stock)
    3. Sends alerts for each item (deduplicated)
    4. Returns summary for monitoring
    
    Args:
        location_id: Optional location filter (None = all locations)
        
    Returns:
        Summary dict with counts and items found
    """
    lock_name = f"check_low_stock:{location_id or 'all'}"
    
    with TaskLock(lock_name, timeout=300) as acquired:
        if not acquired:
            logger.info("Low stock check skipped - already running")
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_check_low_stock_async(location_id))


async def _check_low_stock_async(location_id: str | None) -> dict[str, Any]:
    """Async implementation of low stock check."""
    from src.core.database import async_session_factory
    from src.modules.inventory.repository import inventory_repository
    
    async with async_session_factory() as session:
        # Get low stock items
        low_stock_items = await inventory_repository.get_low_stock_items(
            session,
            location_id=location_id,
        )
        
        # Get out of stock items (subset, but more critical)
        out_of_stock_items = await inventory_repository.get_out_of_stock_items(
            session,
            location_id=location_id,
        )
    
    # Track results
    alerts_sent = 0
    items_found = []
    
    # Out of stock items (CRITICAL)
    out_of_stock_ids = {item.id for item in out_of_stock_items}
    
    for item in out_of_stock_items:
        items_found.append({
            "sku": item.product.sku,
            "product_name": item.product.name,
            "location": item.location.code,
            "current_stock": item.physical_stock,
            "severity": "critical",
        })
        
        # Send critical alert
        result = send_low_stock_alert(
            sku=item.product.sku,
            product_name=item.product.name,
            current_stock=0,
            reorder_point=item.reorder_point,
            location=item.location.code,
        )
        
        if not result.get("suppressed"):
            alerts_sent += 1
    
    # Low stock (but not out of stock) items (WARNING)
    for item in low_stock_items:
        if item.id in out_of_stock_ids:
            continue  # Already handled above
        
        items_found.append({
            "sku": item.product.sku,
            "product_name": item.product.name,
            "location": item.location.code,
            "current_stock": item.physical_stock,
            "reorder_point": item.reorder_point,
            "severity": "warning",
        })
        
        result = send_low_stock_alert(
            sku=item.product.sku,
            product_name=item.product.name,
            current_stock=item.physical_stock,
            reorder_point=item.reorder_point,
            location=item.location.code,
        )
        
        if not result.get("suppressed"):
            alerts_sent += 1
    
    summary = {
        "status": "completed",
        "timestamp": datetime.now(UTC).isoformat(),
        "location_filter": location_id,
        "total_low_stock": len(low_stock_items),
        "total_out_of_stock": len(out_of_stock_items),
        "alerts_sent": alerts_sent,
        "items": items_found[:20],  # Limit for response size
    }
    
    logger.info(
        "Low stock check completed",
        **{k: v for k, v in summary.items() if k != "items"},
    )
    
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# EXPIRY CHECK
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.inventory_tasks.check_expiring_products",
    max_retries=3,
    default_retry_delay=60,
)
def check_expiring_products(
    self,
    days_ahead: int = 7,
    location_id: str | None = None,
) -> dict[str, Any]:
    """
    Check for batches expiring within N days.
    
    This task:
    1. Queries batches with expiry_date within threshold
    2. Groups by urgency (1 day, 3 days, 7 days)
    3. Sends alerts for each batch (deduplicated)
    4. Also checks for already-expired batches
    
    Args:
        days_ahead: How many days to look ahead (default 7)
        location_id: Optional location filter
        
    Returns:
        Summary dict with expiring batches
    """
    lock_name = f"check_expiry:{location_id or 'all'}"
    
    with TaskLock(lock_name, timeout=600) as acquired:
        if not acquired:
            logger.info("Expiry check skipped - already running")
            return {"status": "skipped", "reason": "already_running"}
        
        # Use configured default if not specified
        if days_ahead is None:
            days_ahead = settings.expiry_warning_days
        
        return run_async(_check_expiring_async(days_ahead, location_id))


async def _check_expiring_async(
    days_ahead: int,
    location_id: str | None,
) -> dict[str, Any]:
    """Async implementation of expiry check."""
    from src.core.database import async_session_factory
    from src.modules.inventory.repository import inventory_repository
    
    async with async_session_factory() as session:
        # Get expiring batches
        expiring_batches = await inventory_repository.get_expiring_batches(
            session,
            days_ahead=days_ahead,
            location_id=location_id,
        )
        
        # Get already expired batches (need immediate attention)
        expired_batches = await inventory_repository.get_expired_batches(
            session,
            location_id=location_id,
        )
    
    alerts_sent = 0
    expiring_items = []
    expired_items = []
    
    now = datetime.now(UTC)
    
    # Process already expired batches (CRITICAL)
    for batch in expired_batches:
        item = batch.inventory_item
        days_expired = (now - batch.expiry_date).days if batch.expiry_date else 0
        
        expired_items.append({
            "sku": item.product.sku,
            "product_name": item.product.name,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
            "days_expired": days_expired,
            "location": item.location.code,
        })
        
        # Send critical alert for expired items
        result = get_dispatcher().send(Alert(
            title=f"EXPIRED: {item.product.sku}",
            message=(
                f"**{item.product.name}** has EXPIRED stock that needs disposal.\n"
                f"Batch: {batch.batch_number or 'N/A'} | Qty: {batch.quantity}\n"
                f"Expired: {days_expired} day(s) ago"
            ),
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.EXPIRY,
            data={
                "sku": item.product.sku,
                "batch_number": batch.batch_number,
                "quantity": batch.quantity,
                "days_expired": days_expired,
            },
        ))
        
        if not result.get("suppressed"):
            alerts_sent += 1
    
    # Process expiring batches
    for batch in expiring_batches:
        item = batch.inventory_item
        
        # Calculate days until expiry
        if batch.expiry_date:
            days_until = (batch.expiry_date - now).days
        else:
            days_until = 999
        
        expiring_items.append({
            "sku": item.product.sku,
            "product_name": item.product.name,
            "batch_number": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date.isoformat() if batch.expiry_date else None,
            "days_until_expiry": days_until,
            "location": item.location.code,
        })
        
        result = send_expiry_alert(
            sku=item.product.sku,
            product_name=item.product.name,
            batch_number=batch.batch_number,
            quantity=batch.quantity,
            days_until_expiry=days_until,
            expiry_date=batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "N/A",
        )
        
        if not result.get("suppressed"):
            alerts_sent += 1
    
    summary = {
        "status": "completed",
        "timestamp": datetime.now(UTC).isoformat(),
        "location_filter": location_id,
        "days_ahead": days_ahead,
        "total_expiring": len(expiring_batches),
        "total_expired": len(expired_batches),
        "alerts_sent": alerts_sent,
        "expiring_items": expiring_items[:20],
        "expired_items": expired_items[:20],
    }
    
    logger.info(
        "Expiry check completed",
        total_expiring=len(expiring_batches),
        total_expired=len(expired_batches),
        alerts_sent=alerts_sent,
    )
    
    return summary


# ═══════════════════════════════════════════════════════════════════════════
# CRITICAL OUT-OF-STOCK CHECK (More Frequent)
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.inventory_tasks.check_critical_stock",
    max_retries=2,
    default_retry_delay=30,
)
def check_critical_stock(self) -> dict[str, Any]:
    """
    Fast check for critical stock situations.
    
    Runs more frequently than full low stock check.
    Only alerts on completely out-of-stock items.
    """
    lock_name = "check_critical_stock"
    
    with TaskLock(lock_name, timeout=120) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_check_critical_stock_async())


async def _check_critical_stock_async() -> dict[str, Any]:
    """Check for out of stock items."""
    from src.core.database import async_session_factory
    from src.modules.inventory.repository import inventory_repository
    
    async with async_session_factory() as session:
        out_of_stock = await inventory_repository.get_out_of_stock_items(session)
    
    alerts_sent = 0
    
    for item in out_of_stock:
        result = get_dispatcher().send(Alert(
            title=f"OUT OF STOCK: {item.product.sku}",
            message=(
                f"**{item.product.name}** at {item.location.code} is OUT OF STOCK.\n"
                f"Immediate restocking required."
            ),
            severity=AlertSeverity.CRITICAL,
            category=AlertCategory.OUT_OF_STOCK,
            data={
                "sku": item.product.sku,
                "location": item.location.code,
            },
        ))
        
        if not result.get("suppressed"):
            alerts_sent += 1
    
    return {
        "status": "completed",
        "out_of_stock_count": len(out_of_stock),
        "alerts_sent": alerts_sent,
    }


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY RECONCILIATION (Weekly)
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.inventory_tasks.reconcile_batch_totals",
    max_retries=2,
    default_retry_delay=300,
)
def reconcile_batch_totals(self) -> dict[str, Any]:
    """
    Verify that inventory item totals match sum of batches.
    
    This catches data inconsistencies that might occur due to:
    - Race conditions
    - Partial transaction failures
    - Manual database edits
    
    Runs weekly as a data integrity check.
    """
    lock_name = "reconcile_batch_totals"
    
    with TaskLock(lock_name, timeout=1800) as acquired:  # 30 min timeout
        if not acquired:
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_reconcile_batch_totals_async())


async def _reconcile_batch_totals_async() -> dict[str, Any]:
    """Check batch totals match inventory totals."""
    from sqlalchemy import func, select
    
    from src.core.database import async_session_factory
    from src.modules.inventory.models import InventoryBatch, InventoryItem
    
    discrepancies = []
    
    async with async_session_factory() as session:
        # Get sum of batches per inventory item
        batch_totals = (
            select(
                InventoryBatch.inventory_item_id,
                func.sum(InventoryBatch.quantity).label("batch_total"),
            )
            .where(InventoryBatch.quantity > 0)
            .group_by(InventoryBatch.inventory_item_id)
            .subquery()
        )
        
        # Find inventory items where physical_stock != batch sum
        # Only for items that have batches (perishables)
        query = (
            select(
                InventoryItem.id,
                InventoryItem.physical_stock,
                batch_totals.c.batch_total,
            )
            .join(batch_totals, InventoryItem.id == batch_totals.c.inventory_item_id)
            .where(InventoryItem.physical_stock != batch_totals.c.batch_total)
            .where(InventoryItem.is_active == True)
        )
        
        result = await session.execute(query)
        
        for row in result:
            discrepancies.append({
                "inventory_item_id": row.id,
                "physical_stock": row.physical_stock,
                "batch_total": int(row.batch_total),
                "difference": row.physical_stock - int(row.batch_total),
            })
    
    if discrepancies:
        get_dispatcher().send(Alert(
            title="Inventory Discrepancies Found",
            message=(
                f"Found {len(discrepancies)} items where physical stock "
                f"doesn't match batch totals. Review required."
            ),
            severity=AlertSeverity.WARNING,
            category=AlertCategory.SYSTEM,
            data={"discrepancy_count": len(discrepancies)},
        ))
    
    return {
        "status": "completed",
        "discrepancies_found": len(discrepancies),
        "discrepancies": discrepancies[:50],  # Limit response size
    }
