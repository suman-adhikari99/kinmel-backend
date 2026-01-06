"""
Report Generation Tasks
-----------------------
Scheduled tasks for generating inventory reports and digests.

Tasks:
1. generate_daily_summary - Daily inventory health summary
2. generate_movement_report - Stock movement audit report
3. send_inventory_digest - Email digest to managers

Scheduling:
- Daily summary: Every day at midnight
- Movement report: Weekly on Monday at 1 AM
- Inventory digest: Daily at 8 AM (business hours start)
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta
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
)

settings = get_settings()
logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# DAILY INVENTORY SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.report_tasks.generate_daily_summary",
    max_retries=3,
    default_retry_delay=300,
)
def generate_daily_summary(self) -> dict[str, Any]:
    """
    Generate daily inventory health summary.
    
    Includes:
    - Total SKUs tracked
    - Low stock count
    - Out of stock count
    - Expiring soon count
    - Today's movement summary
    - Top movers (most activity)
    
    Sends summary as notification and returns data for dashboard.
    """
    lock_name = "daily_summary"
    
    with TaskLock(lock_name, timeout=600) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_generate_daily_summary_async())


async def _generate_daily_summary_async() -> dict[str, Any]:
    """Generate daily inventory summary."""
    from sqlalchemy import func, select
    
    from src.core.database import async_session_factory
    from src.modules.inventory.models import (
        InventoryBatch,
        InventoryItem,
        StockMovement,
    )
    from src.modules.products.models import Product
    
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    expiry_threshold = now + timedelta(days=settings.expiry_warning_days)
    
    async with async_session_factory() as session:
        # Total active inventory items
        total_items_result = await session.execute(
            select(func.count(InventoryItem.id))
            .where(InventoryItem.is_active == True)
        )
        total_items = total_items_result.scalar() or 0
        
        # Total active products (unique SKUs)
        total_products_result = await session.execute(
            select(func.count(Product.id))
            .where(Product.is_active == True)
        )
        total_products = total_products_result.scalar() or 0
        
        # Low stock count
        low_stock_result = await session.execute(
            select(func.count(InventoryItem.id))
            .where(
                InventoryItem.physical_stock <= InventoryItem.reorder_point,
                InventoryItem.physical_stock > 0,
                InventoryItem.is_active == True,
            )
        )
        low_stock_count = low_stock_result.scalar() or 0
        
        # Out of stock count
        out_of_stock_result = await session.execute(
            select(func.count(InventoryItem.id))
            .where(
                InventoryItem.physical_stock == 0,
                InventoryItem.is_active == True,
            )
        )
        out_of_stock_count = out_of_stock_result.scalar() or 0
        
        # Expiring soon (within configured days)
        expiring_result = await session.execute(
            select(func.count(InventoryBatch.id))
            .where(
                InventoryBatch.expiry_date <= expiry_threshold,
                InventoryBatch.expiry_date > now,
                InventoryBatch.quantity > 0,
            )
        )
        expiring_count = expiring_result.scalar() or 0
        
        # Already expired
        expired_result = await session.execute(
            select(func.count(InventoryBatch.id))
            .where(
                InventoryBatch.expiry_date < now,
                InventoryBatch.quantity > 0,
            )
        )
        expired_count = expired_result.scalar() or 0
        
        # Today's movements
        movements_result = await session.execute(
            select(
                StockMovement.movement_type,
                func.count(StockMovement.id).label("count"),
                func.sum(func.abs(StockMovement.quantity_delta)).label("total_units"),
            )
            .where(StockMovement.created_at >= today_start)
            .group_by(StockMovement.movement_type)
        )
        
        movements_by_type = {}
        total_movements = 0
        for row in movements_result:
            movements_by_type[row.movement_type] = {
                "count": row.count,
                "total_units": int(row.total_units or 0),
            }
            total_movements += row.count
        
        # Total inventory value (rough estimate)
        value_result = await session.execute(
            select(
                func.sum(InventoryItem.physical_stock * Product.unit_price)
            )
            .join(InventoryItem.product)
            .where(InventoryItem.is_active == True)
        )
        total_value = float(value_result.scalar() or 0)
    
    # Build summary
    summary = {
        "report_date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(),
        "inventory_health": {
            "total_products": total_products,
            "total_inventory_items": total_items,
            "low_stock_items": low_stock_count,
            "out_of_stock_items": out_of_stock_count,
            "expiring_soon_batches": expiring_count,
            "expired_batches": expired_count,
            "estimated_inventory_value": round(total_value, 2),
        },
        "todays_activity": {
            "total_movements": total_movements,
            "by_type": movements_by_type,
        },
        "health_score": _calculate_health_score(
            total_items,
            low_stock_count,
            out_of_stock_count,
            expired_count,
        ),
    }
    
    # Send summary notification
    health_emoji = "🟢" if summary["health_score"] >= 80 else "🟡" if summary["health_score"] >= 60 else "🔴"
    
    get_dispatcher().send(Alert(
        title=f"{health_emoji} Daily Inventory Summary - {now.strftime('%Y-%m-%d')}",
        message=(
            f"**Health Score: {summary['health_score']}%**\n\n"
            f"📦 Products: {total_products} | Inventory Items: {total_items}\n"
            f"⚠️ Low Stock: {low_stock_count} | ❌ Out of Stock: {out_of_stock_count}\n"
            f"🕐 Expiring Soon: {expiring_count} | ☠️ Expired: {expired_count}\n"
            f"📊 Today's Movements: {total_movements}\n"
            f"💰 Est. Value: ${total_value:,.2f}"
        ),
        severity=AlertSeverity.INFO,
        category=AlertCategory.REPORT,
        data=summary["inventory_health"],
    ))
    
    logger.info(
        "Daily summary generated",
        health_score=summary["health_score"],
        total_products=total_products,
        low_stock=low_stock_count,
        out_of_stock=out_of_stock_count,
    )
    
    return summary


def _calculate_health_score(
    total_items: int,
    low_stock: int,
    out_of_stock: int,
    expired: int,
) -> int:
    """
    Calculate inventory health score (0-100).
    
    Factors:
    - Out of stock items (highest penalty)
    - Low stock items (medium penalty)
    - Expired batches (high penalty)
    """
    if total_items == 0:
        return 100
    
    # Start at 100
    score = 100.0
    
    # Penalty for out of stock (5 points each, max 30)
    out_of_stock_penalty = min(out_of_stock * 5, 30)
    score -= out_of_stock_penalty
    
    # Penalty for low stock (2 points each, max 20)
    low_stock_penalty = min(low_stock * 2, 20)
    score -= low_stock_penalty
    
    # Penalty for expired (3 points each, max 20)
    expired_penalty = min(expired * 3, 20)
    score -= expired_penalty
    
    # Penalty for high percentage of problem items
    problem_ratio = (low_stock + out_of_stock) / total_items
    if problem_ratio > 0.2:
        score -= 10
    elif problem_ratio > 0.1:
        score -= 5
    
    return max(0, min(100, int(score)))


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY DIGEST EMAIL
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.report_tasks.send_inventory_digest",
    max_retries=3,
    default_retry_delay=300,
)
def send_inventory_digest(self) -> dict[str, Any]:
    """
    Send inventory digest to managers.
    
    Morning digest includes:
    - Yesterday's summary
    - Items needing attention today
    - Expiring items this week
    - Top moving products
    """
    lock_name = "inventory_digest"
    
    with TaskLock(lock_name, timeout=600) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_send_inventory_digest_async())


async def _send_inventory_digest_async() -> dict[str, Any]:
    """Generate and send inventory digest."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import joinedload
    
    from src.core.database import async_session_factory
    from src.modules.inventory.models import (
        InventoryBatch,
        InventoryItem,
        StockMovement,
    )
    
    now = datetime.now(UTC)
    yesterday_start = (now - timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_ahead = now + timedelta(days=7)
    
    async with async_session_factory() as session:
        # Get items needing attention (low stock or out of stock)
        attention_items_result = await session.execute(
            select(InventoryItem)
            .options(
                joinedload(InventoryItem.product),
                joinedload(InventoryItem.location),
            )
            .where(
                InventoryItem.physical_stock <= InventoryItem.reorder_point,
                InventoryItem.is_active == True,
            )
            .order_by(InventoryItem.physical_stock.asc())
            .limit(10)
        )
        attention_items = attention_items_result.scalars().all()
        
        # Get expiring this week
        expiring_result = await session.execute(
            select(InventoryBatch)
            .join(InventoryBatch.inventory_item)
            .options(
                joinedload(InventoryBatch.inventory_item).joinedload(InventoryItem.product),
            )
            .where(
                InventoryBatch.expiry_date <= week_ahead,
                InventoryBatch.expiry_date > now,
                InventoryBatch.quantity > 0,
            )
            .order_by(InventoryBatch.expiry_date.asc())
            .limit(10)
        )
        expiring_batches = expiring_result.scalars().all()
        
        # Yesterday's top movers (most movements)
        top_movers_result = await session.execute(
            select(
                StockMovement.inventory_item_id,
                func.count(StockMovement.id).label("movement_count"),
                func.sum(func.abs(StockMovement.quantity_delta)).label("total_units"),
            )
            .where(StockMovement.created_at >= yesterday_start)
            .group_by(StockMovement.inventory_item_id)
            .order_by(func.count(StockMovement.id).desc())
            .limit(5)
        )
        top_movers = []
        for row in top_movers_result:
            top_movers.append({
                "inventory_item_id": row.inventory_item_id,
                "movement_count": row.movement_count,
                "total_units": int(row.total_units or 0),
            })
    
    # Format attention items
    attention_list = []
    for item in attention_items:
        attention_list.append({
            "sku": item.product.sku,
            "name": item.product.name,
            "location": item.location.code,
            "stock": item.physical_stock,
            "reorder_point": item.reorder_point,
            "status": "OUT OF STOCK" if item.physical_stock == 0 else "LOW STOCK",
        })
    
    # Format expiring items
    expiring_list = []
    for batch in expiring_batches:
        item = batch.inventory_item
        days_until = (batch.expiry_date - now).days if batch.expiry_date else 999
        expiring_list.append({
            "sku": item.product.sku,
            "name": item.product.name,
            "batch": batch.batch_number,
            "quantity": batch.quantity,
            "expiry_date": batch.expiry_date.strftime("%Y-%m-%d") if batch.expiry_date else "N/A",
            "days_until": days_until,
        })
    
    digest = {
        "generated_at": now.isoformat(),
        "period": f"{yesterday_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
        "items_needing_attention": attention_list,
        "expiring_this_week": expiring_list,
        "top_movers_yesterday": top_movers,
    }
    
    # Build digest message
    message_parts = [
        f"**📅 Inventory Digest - {now.strftime('%A, %B %d, %Y')}**\n",
    ]
    
    if attention_list:
        message_parts.append(f"\n**🚨 Items Needing Attention ({len(attention_list)})**")
        for item in attention_list[:5]:
            emoji = "❌" if item["status"] == "OUT OF STOCK" else "⚠️"
            message_parts.append(
                f"  {emoji} {item['sku']} - {item['name']} @ {item['location']}: "
                f"{item['stock']}/{item['reorder_point']}"
            )
    
    if expiring_list:
        message_parts.append(f"\n**🕐 Expiring This Week ({len(expiring_list)})**")
        for item in expiring_list[:5]:
            message_parts.append(
                f"  ⏰ {item['sku']} - {item['name']}: "
                f"{item['quantity']} units expire in {item['days_until']} days"
            )
    
    if not attention_list and not expiring_list:
        message_parts.append("\n✅ All clear! No items need immediate attention.")
    
    # Send digest
    get_dispatcher().send(Alert(
        title=f"📊 Morning Inventory Digest - {now.strftime('%Y-%m-%d')}",
        message="\n".join(message_parts),
        severity=AlertSeverity.INFO,
        category=AlertCategory.REPORT,
        data={
            "attention_count": len(attention_list),
            "expiring_count": len(expiring_list),
        },
    ))
    
    logger.info(
        "Inventory digest sent",
        attention_items=len(attention_list),
        expiring_items=len(expiring_list),
    )
    
    return digest


# ═══════════════════════════════════════════════════════════════════════════
# MOVEMENT AUDIT REPORT (Weekly)
# ═══════════════════════════════════════════════════════════════════════════


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.report_tasks.generate_movement_report",
    max_retries=3,
    default_retry_delay=600,
)
def generate_movement_report(
    self,
    days: int = 7,
) -> dict[str, Any]:
    """
    Generate stock movement audit report.
    
    Summarizes all stock changes over the period:
    - By movement type
    - By user
    - By product category
    - Anomaly detection (unusual patterns)
    """
    lock_name = "movement_report"
    
    with TaskLock(lock_name, timeout=1800) as acquired:
        if not acquired:
            return {"status": "skipped", "reason": "already_running"}
        
        return run_async(_generate_movement_report_async(days))


async def _generate_movement_report_async(days: int) -> dict[str, Any]:
    """Generate movement report."""
    from sqlalchemy import func, select
    from sqlalchemy.orm import joinedload
    
    from src.core.database import async_session_factory
    from src.modules.inventory.models import InventoryItem, StockMovement
    from src.modules.products.models import Product
    from src.modules.users.models import User
    
    now = datetime.now(UTC)
    start_date = now - timedelta(days=days)
    
    async with async_session_factory() as session:
        # Movements by type
        by_type_result = await session.execute(
            select(
                StockMovement.movement_type,
                func.count(StockMovement.id).label("count"),
                func.sum(StockMovement.quantity_delta).label("net_change"),
                func.sum(func.abs(StockMovement.quantity_delta)).label("total_volume"),
            )
            .where(StockMovement.created_at >= start_date)
            .group_by(StockMovement.movement_type)
        )
        
        by_type = {}
        for row in by_type_result:
            by_type[row.movement_type] = {
                "count": row.count,
                "net_change": int(row.net_change or 0),
                "total_volume": int(row.total_volume or 0),
            }
        
        # Movements by user
        by_user_result = await session.execute(
            select(
                User.email,
                User.full_name,
                func.count(StockMovement.id).label("count"),
            )
            .join(StockMovement, StockMovement.user_id == User.id)
            .where(StockMovement.created_at >= start_date)
            .group_by(User.id, User.email, User.full_name)
            .order_by(func.count(StockMovement.id).desc())
            .limit(10)
        )
        
        by_user = []
        for row in by_user_result:
            by_user.append({
                "email": row.email,
                "name": row.full_name,
                "movement_count": row.count,
            })
        
        # Total counts
        total_result = await session.execute(
            select(
                func.count(StockMovement.id),
                func.sum(StockMovement.quantity_delta),
            )
            .where(StockMovement.created_at >= start_date)
        )
        total_row = total_result.one()
        
        # Large adjustments (potential anomalies)
        large_adjustments_result = await session.execute(
            select(StockMovement)
            .options(
                joinedload(StockMovement.inventory_item).joinedload(InventoryItem.product),
            )
            .where(
                StockMovement.created_at >= start_date,
                func.abs(StockMovement.quantity_delta) > 100,  # Threshold
            )
            .order_by(func.abs(StockMovement.quantity_delta).desc())
            .limit(10)
        )
        
        large_adjustments = []
        for movement in large_adjustments_result.scalars():
            large_adjustments.append({
                "movement_id": movement.id,
                "sku": movement.inventory_item.product.sku if movement.inventory_item else "N/A",
                "type": movement.movement_type,
                "delta": movement.quantity_delta,
                "reason": movement.reason,
                "created_at": movement.created_at.isoformat(),
            })
    
    report = {
        "report_type": "movement_audit",
        "generated_at": now.isoformat(),
        "period": {
            "start": start_date.isoformat(),
            "end": now.isoformat(),
            "days": days,
        },
        "summary": {
            "total_movements": total_row[0] or 0,
            "net_stock_change": int(total_row[1] or 0),
        },
        "by_type": by_type,
        "by_user": by_user,
        "large_adjustments": large_adjustments,
    }
    
    # Send report notification
    get_dispatcher().send(Alert(
        title=f"📊 Weekly Movement Report - {start_date.strftime('%m/%d')} to {now.strftime('%m/%d')}",
        message=(
            f"**Period:** {days} days\n"
            f"**Total Movements:** {report['summary']['total_movements']}\n"
            f"**Net Stock Change:** {report['summary']['net_stock_change']:+d} units\n"
            f"**Large Adjustments:** {len(large_adjustments)} (>100 units)"
        ),
        severity=AlertSeverity.INFO,
        category=AlertCategory.REPORT,
        data=report["summary"],
    ))
    
    logger.info(
        "Movement report generated",
        total_movements=report["summary"]["total_movements"],
        period_days=days,
    )
    
    return report
