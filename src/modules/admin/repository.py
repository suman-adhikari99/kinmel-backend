"""
Admin Repository
----------------
Data access layer for audit and admin queries.

Design Principles:
1. Read-only operations (audit logs are immutable)
2. Efficient pagination with total counts
3. Flexible filtering with proper indexing
4. Privacy-aware (joins user name, not email)
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import Row, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.logging import LoggerMixin
from src.modules.admin.schemas import (
    ActionTypeStats,
    AuditActionType,
    AuditLogEntry,
    AuditLogQueryParams,
    AuditReasonType,
    DailyActivityStats,
)
from src.modules.inventory.models import (
    InventoryItem,
    Location,
    StockMovement,
)
from src.modules.products.models import Product
from src.modules.users.models import User


class AuditRepository(LoggerMixin):
    """
    Repository for audit log queries.
    
    All methods are read-only and optimized for reporting workloads.
    """
    
    async def get_audit_logs(
        self,
        session: AsyncSession,
        params: AuditLogQueryParams,
    ) -> tuple[list[AuditLogEntry], int]:
        """
        Query audit logs with filters and pagination.
        
        Args:
            session: Database session
            params: Query parameters (filters, pagination)
            
        Returns:
            Tuple of (list of entries, total count)
        """
        # Build base query with joins
        query = (
            select(
                StockMovement,
                Product.sku,
                Product.name.label("product_name"),
                Location.code.label("location_code"),
                Location.name.label("location_name"),
                User.full_name.label("user_name"),
            )
            .join(
                InventoryItem,
                StockMovement.inventory_item_id == InventoryItem.id,
            )
            .join(
                Product,
                InventoryItem.product_id == Product.id,
            )
            .join(
                Location,
                InventoryItem.location_id == Location.id,
            )
            .join(
                User,
                StockMovement.user_id == User.id,
            )
        )
        
        # Build filters list
        filters = []
        applied_filters = {}
        
        # SKU filter
        if params.sku:
            filters.append(Product.sku == params.sku)
            applied_filters["sku"] = params.sku
        
        # Location filter
        if params.location_code:
            filters.append(Location.code == params.location_code)
            applied_filters["location_code"] = params.location_code
        
        # Action type filter
        if params.action_type:
            filters.append(StockMovement.movement_type == params.action_type.value)
            applied_filters["action_type"] = params.action_type.value
        
        # Reason filter
        if params.reason:
            filters.append(StockMovement.reason == params.reason.value)
            applied_filters["reason"] = params.reason.value
        
        # User filter (partial match on name)
        if params.performed_by:
            filters.append(
                User.full_name.ilike(f"%{params.performed_by}%")
            )
            applied_filters["performed_by"] = params.performed_by
        
        # Date range filters
        if params.start_date:
            filters.append(StockMovement.created_at >= params.start_date)
            applied_filters["start_date"] = params.start_date.isoformat()
        
        if params.end_date:
            filters.append(StockMovement.created_at <= params.end_date)
            applied_filters["end_date"] = params.end_date.isoformat()
        
        # Reference filter
        if params.reference_id:
            filters.append(StockMovement.reference_id == params.reference_id)
            applied_filters["reference_id"] = params.reference_id
        
        # Apply all filters
        if filters:
            query = query.where(and_(*filters))
        
        # Get total count
        count_query = (
            select(func.count())
            .select_from(StockMovement)
            .join(InventoryItem, StockMovement.inventory_item_id == InventoryItem.id)
            .join(Product, InventoryItem.product_id == Product.id)
            .join(Location, InventoryItem.location_id == Location.id)
            .join(User, StockMovement.user_id == User.id)
        )
        
        if filters:
            count_query = count_query.where(and_(*filters))
        
        count_result = await session.execute(count_query)
        total = count_result.scalar() or 0
        
        # Apply ordering (newest first)
        query = query.order_by(StockMovement.created_at.desc())
        
        # Apply pagination
        query = query.limit(params.limit).offset(params.offset)
        
        # Execute query
        result = await session.execute(query)
        rows = result.all()
        
        # Transform to response model
        entries = []
        for row in rows:
            movement = row[0]
            entries.append(AuditLogEntry(
                sku=row.sku,
                product_name=row.product_name,
                location_code=row.location_code,
                location_name=row.location_name,
                action_type=AuditActionType(movement.movement_type),
                reason=movement.reason,
                quantity_delta=movement.quantity_delta,
                quantity_before=movement.quantity_before,
                quantity_after=movement.quantity_after,
                performed_by=row.user_name,
                timestamp=movement.created_at,
                reference_id=movement.reference_id,
                reference_type=movement.reference_type,
                notes=movement.notes,
            ))
        
        self.logger.info(
            "Audit log query executed",
            total_results=total,
            returned=len(entries),
            filters=applied_filters,
        )
        
        return entries, total, applied_filters
    
    async def get_audit_stats(
        self,
        session: AsyncSession,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get aggregated audit statistics.
        
        Args:
            session: Database session
            start_date: Period start (default: 30 days ago)
            end_date: Period end (default: now)
            
        Returns:
            Statistics dictionary
        """
        now = datetime.now(UTC)
        
        if end_date is None:
            end_date = now
        
        if start_date is None:
            start_date = now - timedelta(days=30)
        
        # Build date filter
        date_filter = and_(
            StockMovement.created_at >= start_date,
            StockMovement.created_at <= end_date,
        )
        
        # ─────────────────────────────────────────────────────────────
        # Total stats
        # ─────────────────────────────────────────────────────────────
        
        total_query = select(
            func.count(StockMovement.id).label("total_actions"),
            func.sum(
                case(
                    (StockMovement.quantity_delta > 0, StockMovement.quantity_delta),
                    else_=0,
                )
            ).label("total_increased"),
            func.sum(
                case(
                    (StockMovement.quantity_delta < 0, func.abs(StockMovement.quantity_delta)),
                    else_=0,
                )
            ).label("total_decreased"),
        ).where(date_filter)
        
        total_result = await session.execute(total_query)
        total_row = total_result.one()
        
        # ─────────────────────────────────────────────────────────────
        # Stats by action type
        # ─────────────────────────────────────────────────────────────
        
        by_type_query = (
            select(
                StockMovement.movement_type,
                func.count(StockMovement.id).label("count"),
                func.sum(func.abs(StockMovement.quantity_delta)).label("total_units"),
            )
            .where(date_filter)
            .group_by(StockMovement.movement_type)
            .order_by(func.count(StockMovement.id).desc())
        )
        
        by_type_result = await session.execute(by_type_query)
        by_type = []
        
        for row in by_type_result:
            try:
                action_type = AuditActionType(row.movement_type)
                by_type.append(ActionTypeStats(
                    action_type=action_type,
                    count=row.count,
                    total_units_affected=int(row.total_units or 0),
                ))
            except ValueError:
                # Skip unknown action types
                pass
        
        # ─────────────────────────────────────────────────────────────
        # Stats by day
        # ─────────────────────────────────────────────────────────────
        
        by_day_query = (
            select(
                func.date(StockMovement.created_at).label("date"),
                func.count(StockMovement.id).label("total_actions"),
                func.sum(
                    case(
                        (StockMovement.quantity_delta > 0, StockMovement.quantity_delta),
                        else_=0,
                    )
                ).label("increased"),
                func.sum(
                    case(
                        (StockMovement.quantity_delta < 0, func.abs(StockMovement.quantity_delta)),
                        else_=0,
                    )
                ).label("decreased"),
            )
            .where(date_filter)
            .group_by(func.date(StockMovement.created_at))
            .order_by(func.date(StockMovement.created_at).desc())
            .limit(30)  # Last 30 days
        )
        
        by_day_result = await session.execute(by_day_query)
        by_day = []
        
        for row in by_day_result:
            by_day.append(DailyActivityStats(
                date=str(row.date),
                total_actions=row.total_actions,
                total_units_increased=int(row.increased or 0),
                total_units_decreased=int(row.decreased or 0),
            ))
        
        # ─────────────────────────────────────────────────────────────
        # Top products (most movements)
        # ─────────────────────────────────────────────────────────────
        
        top_products_query = (
            select(
                Product.sku,
                Product.name,
                func.count(StockMovement.id).label("movement_count"),
            )
            .join(InventoryItem, StockMovement.inventory_item_id == InventoryItem.id)
            .join(Product, InventoryItem.product_id == Product.id)
            .where(date_filter)
            .group_by(Product.id, Product.sku, Product.name)
            .order_by(func.count(StockMovement.id).desc())
            .limit(10)
        )
        
        top_products_result = await session.execute(top_products_query)
        top_products = [
            {"sku": row.sku, "name": row.name, "movement_count": row.movement_count}
            for row in top_products_result
        ]
        
        # ─────────────────────────────────────────────────────────────
        # Top users (most actions)
        # ─────────────────────────────────────────────────────────────
        
        top_users_query = (
            select(
                User.full_name,
                func.count(StockMovement.id).label("action_count"),
            )
            .join(User, StockMovement.user_id == User.id)
            .where(date_filter)
            .group_by(User.id, User.full_name)
            .order_by(func.count(StockMovement.id).desc())
            .limit(10)
        )
        
        top_users_result = await session.execute(top_users_query)
        top_users = [
            {"name": row.full_name, "action_count": row.action_count}
            for row in top_users_result
        ]
        
        return {
            "period_start": start_date,
            "period_end": end_date,
            "total_actions": total_row.total_actions or 0,
            "total_units_increased": int(total_row.total_increased or 0),
            "total_units_decreased": int(total_row.total_decreased or 0),
            "by_action_type": by_type,
            "by_day": by_day,
            "top_products": top_products,
            "top_users": top_users,
        }
    
    async def export_audit_logs_csv(
        self,
        session: AsyncSession,
        params: AuditLogQueryParams,
    ) -> list[dict[str, Any]]:
        """
        Export audit logs as list of dicts for CSV generation.
        
        Same as get_audit_logs but returns flat dict structure
        suitable for CSV export.
        """
        entries, total, _ = await self.get_audit_logs(session, params)
        
        # Convert to flat dict structure for CSV
        return [
            {
                "timestamp": entry.timestamp.isoformat(),
                "sku": entry.sku,
                "product_name": entry.product_name,
                "location_code": entry.location_code,
                "location_name": entry.location_name,
                "action_type": entry.action_type.value,
                "reason": entry.reason or "",
                "quantity_delta": entry.quantity_delta,
                "quantity_before": entry.quantity_before,
                "quantity_after": entry.quantity_after,
                "performed_by": entry.performed_by,
                "reference_id": entry.reference_id or "",
                "reference_type": entry.reference_type or "",
                "notes": entry.notes or "",
            }
            for entry in entries
        ]


# Singleton instance
audit_repository = AuditRepository()
