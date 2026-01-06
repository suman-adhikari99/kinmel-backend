"""
Dashboard Repository
--------------------
Database queries for dashboard statistics.

Maps available data to dashboard metrics:
- Orders → StockMovements with SALE type
- Products → Products table
- Customers → Mock data (no customers table yet)
- Activity → StockMovements
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import func, select, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.inventory.models import (
    InventoryItem,
    StockMovement,
    MovementType,
)
from src.modules.products.models import Product
from src.modules.users.models import User
from src.modules.dashboard.schemas import (
    OrdersStats,
    ProductsStats,
    CustomersStats,
    RecentOrder,
    RecentActivity,
    DashboardResponse,
)


class DashboardRepository:
    """
    Repository for dashboard statistics queries.
    
    Since the system doesn't have dedicated Orders/Customers tables,
    we derive metrics from available data:
    - Sales count from StockMovements (type=SALE)
    - Revenue estimated from product prices × quantities
    - Customer data is mocked for now
    """
    
    async def get_orders_stats(self, db: AsyncSession) -> OrdersStats:
        """
        Get order statistics derived from stock movements.
        
        Maps SALE movements to "orders" for dashboard display.
        """
        now = datetime.now(UTC)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        
        # Count today's sales (as orders)
        today_sales_query = select(
            func.count(StockMovement.id).label("count"),
            func.coalesce(func.sum(func.abs(StockMovement.quantity_delta)), 0).label("units")
        ).where(
            and_(
                StockMovement.movement_type == MovementType.SALE,
                StockMovement.created_at >= today_start
            )
        )
        
        today_result = await db.execute(today_sales_query)
        today_row = today_result.one()
        today_count = today_row.count or 0
        today_units = today_row.units or 0
        
        # Estimate today's revenue (units × average product price)
        avg_price_query = select(func.avg(Product.unit_price)).where(Product.is_active == True)
        avg_price_result = await db.execute(avg_price_query)
        avg_price = avg_price_result.scalar() or Decimal("10.00")
        today_revenue = Decimal(str(today_units)) * Decimal(str(avg_price))
        
        # Count yesterday's sales
        yesterday_sales_query = select(
            func.count(StockMovement.id).label("count"),
            func.coalesce(func.sum(func.abs(StockMovement.quantity_delta)), 0).label("units")
        ).where(
            and_(
                StockMovement.movement_type == MovementType.SALE,
                StockMovement.created_at >= yesterday_start,
                StockMovement.created_at < today_start
            )
        )
        
        yesterday_result = await db.execute(yesterday_sales_query)
        yesterday_row = yesterday_result.one()
        yesterday_count = yesterday_row.count or 0
        yesterday_units = yesterday_row.units or 0
        yesterday_revenue = Decimal(str(yesterday_units)) * Decimal(str(avg_price))
        
        # Count reservations as "pending" orders
        pending_query = select(func.count(StockMovement.id)).where(
            and_(
                StockMovement.movement_type == MovementType.RESERVATION,
                StockMovement.created_at >= today_start - timedelta(days=7)
            )
        )
        pending_result = await db.execute(pending_query)
        pending_count = pending_result.scalar() or 0
        
        # Mock ready_for_pickup and out_for_delivery since we don't have order status
        ready_for_pickup = min(pending_count // 2, 5) if pending_count > 0 else 0
        out_for_delivery = min(pending_count // 3, 3) if pending_count > 0 else 0
        
        return OrdersStats(
            today_count=today_count,
            today_revenue=round(today_revenue, 2),
            pending_count=pending_count,
            ready_for_pickup=ready_for_pickup,
            out_for_delivery=out_for_delivery,
            yesterday_count=yesterday_count,
            yesterday_revenue=round(yesterday_revenue, 2),
        )
    
    async def get_products_stats(self, db: AsyncSession) -> ProductsStats:
        """Get product statistics."""
        
        # Count active products
        active_query = select(func.count(Product.id)).where(
            Product.is_active == True
        )
        active_result = await db.execute(active_query)
        total_active = active_result.scalar() or 0
        
        # Count low stock items (where physical_stock <= reorder_point)
        low_stock_query = select(func.count(InventoryItem.id)).where(
            and_(
                InventoryItem.is_active == True,
                InventoryItem.physical_stock <= InventoryItem.reorder_point
            )
        )
        low_stock_result = await db.execute(low_stock_query)
        low_stock_count = low_stock_result.scalar() or 0
        
        return ProductsStats(
            total_active=total_active,
            low_stock_count=low_stock_count,
        )
    
    async def get_customers_stats(self, db: AsyncSession) -> CustomersStats:
        """
        Get customer statistics.
        
        Note: No dedicated customers table exists yet.
        Using user count as placeholder metric.
        """
        # Count active users as proxy for "customers"
        # In a real system, this would query a customers table
        users_query = select(func.count(User.id)).where(
            User.is_active == True
        )
        users_result = await db.execute(users_query)
        active_count = users_result.scalar() or 0
        
        # Mock last week count (slightly less for trend visualization)
        last_week_count = max(active_count - 2, 0)
        
        return CustomersStats(
            active_count=active_count,
            last_week_count=last_week_count,
        )
    
    async def get_recent_orders(
        self,
        db: AsyncSession,
        limit: int = 5
    ) -> list[RecentOrder]:
        """
        Get recent orders (derived from SALE movements).
        
        Groups sales by reference_id to approximate orders.
        """
        # Get recent sale movements
        sales_query = (
            select(
                StockMovement.id,
                StockMovement.reference_id,
                StockMovement.quantity_delta,
                StockMovement.created_at,
                User.full_name.label("customer_name"),
                Product.unit_price,
            )
            .join(User, StockMovement.user_id == User.id)
            .join(InventoryItem, StockMovement.inventory_item_id == InventoryItem.id)
            .join(Product, InventoryItem.product_id == Product.id)
            .where(StockMovement.movement_type == MovementType.SALE)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
        )
        
        result = await db.execute(sales_query)
        rows = result.all()
        
        orders = []
        for row in rows:
            order_total = abs(row.quantity_delta) * (row.unit_price or Decimal("10.00"))
            orders.append(RecentOrder(
                id=row.reference_id or row.id,
                customer_name=row.customer_name or "Walk-in Customer",
                total=round(order_total, 2),
                status="completed",
                items_count=abs(row.quantity_delta),
                created_at=row.created_at,
            ))
        
        return orders
    
    async def get_recent_activity(
        self,
        db: AsyncSession,
        limit: int = 10
    ) -> list[RecentActivity]:
        """Get recent system activity from stock movements."""
        
        activity_query = (
            select(
                StockMovement.id,
                StockMovement.movement_type,
                StockMovement.quantity_delta,
                StockMovement.created_at,
                StockMovement.notes,
                User.full_name.label("user_name"),
                Product.sku,
                Product.name.label("product_name"),
            )
            .join(User, StockMovement.user_id == User.id)
            .join(InventoryItem, StockMovement.inventory_item_id == InventoryItem.id)
            .join(Product, InventoryItem.product_id == Product.id)
            .order_by(StockMovement.created_at.desc())
            .limit(limit)
        )
        
        result = await db.execute(activity_query)
        rows = result.all()
        
        activities = []
        for row in rows:
            # Generate human-readable description
            action = row.movement_type.value if row.movement_type else "unknown"
            delta = row.quantity_delta or 0
            
            if action == "sale":
                description = f"Sold {abs(delta)} units of {row.product_name}"
            elif action == "receiving":
                description = f"Received {delta} units of {row.product_name}"
            elif action == "adjustment":
                direction = "increased" if delta > 0 else "decreased"
                description = f"Stock {direction} by {abs(delta)} for {row.product_name}"
            elif action == "transfer":
                description = f"Transferred {abs(delta)} units of {row.product_name}"
            elif action == "disposal":
                description = f"Disposed {abs(delta)} units of {row.product_name}"
            elif action == "return":
                description = f"Returned {delta} units of {row.product_name}"
            elif action == "reservation":
                description = f"Reserved {abs(delta)} units of {row.product_name}"
            else:
                description = f"{action.title()}: {abs(delta)} units of {row.product_name}"
            
            activities.append(RecentActivity(
                id=row.id,
                action=action,
                description=description,
                user_name=row.user_name or "System",
                timestamp=row.created_at,
                sku=row.sku,
                quantity=abs(delta) if delta else None,
            ))
        
        return activities
    
    async def get_dashboard(self, db: AsyncSession) -> DashboardResponse:
        """Get complete dashboard data."""
        
        orders = await self.get_orders_stats(db)
        products = await self.get_products_stats(db)
        customers = await self.get_customers_stats(db)
        recent_orders = await self.get_recent_orders(db)
        recent_activity = await self.get_recent_activity(db)
        
        return DashboardResponse(
            orders=orders,
            products=products,
            customers=customers,
            recent_orders=recent_orders,
            recent_activity=recent_activity,
        )


# Singleton instance
dashboard_repository = DashboardRepository()

