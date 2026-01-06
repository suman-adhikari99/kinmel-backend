"""
Dashboard API Schemas
---------------------
Pydantic models for dashboard statistics and metrics.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ═══════════════════════════════════════════════════════════════════════════
# ORDER STATISTICS
# ═══════════════════════════════════════════════════════════════════════════


class OrdersStats(BaseModel):
    """Order statistics for dashboard."""
    
    today_count: int = Field(
        description="Number of orders placed today"
    )
    today_revenue: Decimal = Field(
        description="Total revenue from today's orders"
    )
    pending_count: int = Field(
        description="Orders pending processing"
    )
    ready_for_pickup: int = Field(
        description="Orders ready for customer pickup"
    )
    out_for_delivery: int = Field(
        description="Orders currently out for delivery"
    )
    yesterday_count: int = Field(
        description="Number of orders placed yesterday (for trend)"
    )
    yesterday_revenue: Decimal = Field(
        description="Revenue from yesterday's orders (for trend)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# PRODUCT STATISTICS
# ═══════════════════════════════════════════════════════════════════════════


class ProductsStats(BaseModel):
    """Product statistics for dashboard."""
    
    total_active: int = Field(
        description="Total number of active products"
    )
    low_stock_count: int = Field(
        description="Number of products with low stock"
    )


# ═══════════════════════════════════════════════════════════════════════════
# CUSTOMER STATISTICS
# ═══════════════════════════════════════════════════════════════════════════


class CustomersStats(BaseModel):
    """Customer statistics for dashboard."""
    
    active_count: int = Field(
        description="Number of active customers"
    )
    last_week_count: int = Field(
        description="Customer count from last week (for trend)"
    )


# ═══════════════════════════════════════════════════════════════════════════
# RECENT ORDER
# ═══════════════════════════════════════════════════════════════════════════


class RecentOrder(BaseModel):
    """Summary of a recent order."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(description="Order ID")
    customer_name: str = Field(description="Customer name")
    total: Decimal = Field(description="Order total amount")
    status: str = Field(description="Order status")
    items_count: int = Field(description="Number of items in order")
    created_at: datetime = Field(description="When order was placed")


# ═══════════════════════════════════════════════════════════════════════════
# RECENT ACTIVITY
# ═══════════════════════════════════════════════════════════════════════════


class RecentActivity(BaseModel):
    """Summary of recent system activity."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str = Field(description="Activity ID")
    action: str = Field(description="Action type (e.g., 'sale', 'receiving')")
    description: str = Field(description="Human-readable description")
    user_name: str = Field(description="User who performed the action")
    timestamp: datetime = Field(description="When the activity occurred")
    sku: str | None = Field(default=None, description="Related product SKU")
    quantity: int | None = Field(default=None, description="Quantity affected")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD RESPONSE
# ═══════════════════════════════════════════════════════════════════════════


class DashboardResponse(BaseModel):
    """
    Complete dashboard statistics response.
    
    Aggregates metrics across orders, products, customers,
    and recent activity for admin dashboard display.
    """
    
    orders: OrdersStats = Field(
        description="Order statistics and counts"
    )
    products: ProductsStats = Field(
        description="Product statistics"
    )
    customers: CustomersStats = Field(
        description="Customer statistics"
    )
    recent_orders: list[RecentOrder] = Field(
        default_factory=list,
        description="Last 5 orders"
    )
    recent_activity: list[RecentActivity] = Field(
        default_factory=list,
        description="Last 10 system activities"
    )

