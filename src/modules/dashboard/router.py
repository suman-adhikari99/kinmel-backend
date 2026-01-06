"""
Dashboard API Router
--------------------
REST endpoint for dashboard statistics.

🔐 ACCESS CONTROL:
Requires authentication. Available to all authenticated users.
"""

from fastapi import APIRouter

from src.api.deps import CurrentUser, DbSession
from src.core.logging import get_logger
from src.modules.dashboard.repository import dashboard_repository
from src.modules.dashboard.schemas import DashboardResponse

logger = get_logger(__name__)


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
    responses={
        401: {"description": "Not authenticated"},
    },
)


@router.get(
    "/stats",
    response_model=DashboardResponse,
    summary="Get dashboard statistics",
    description="""
    Get aggregated statistics for the admin dashboard.
    
    **Access:** All authenticated users
    
    **Response includes:**
    - **orders**: Today's orders, revenue, pending counts, and yesterday's data for trends
    - **products**: Total active products and low stock count
    - **customers**: Active customer count and last week count for trends
    - **recent_orders**: Last 5 orders
    - **recent_activity**: Last 10 system activities
    
    **Note:** Order data is derived from stock movements (SALE type).
    Customer data is based on user counts until a dedicated customers table is implemented.
    """,
    responses={
        200: {
            "description": "Dashboard statistics",
            "content": {
                "application/json": {
                    "example": {
                        "orders": {
                            "today_count": 47,
                            "today_revenue": 3847.50,
                            "pending_count": 8,
                            "ready_for_pickup": 5,
                            "out_for_delivery": 3,
                            "yesterday_count": 42,
                            "yesterday_revenue": 3560.00
                        },
                        "products": {
                            "total_active": 1284,
                            "low_stock_count": 12
                        },
                        "customers": {
                            "active_count": 892,
                            "last_week_count": 850
                        },
                        "recent_orders": [
                            {
                                "id": "ORD-2024-001",
                                "customer_name": "John Smith",
                                "total": 45.99,
                                "status": "completed",
                                "items_count": 3,
                                "created_at": "2024-01-15T14:30:00Z"
                            }
                        ],
                        "recent_activity": [
                            {
                                "id": "act-123",
                                "action": "sale",
                                "description": "Sold 2 units of Whole Milk 2L",
                                "user_name": "Jane Doe",
                                "timestamp": "2024-01-15T14:30:00Z",
                                "sku": "MILK-2L-WHOLE",
                                "quantity": 2
                            }
                        ]
                    }
                }
            }
        }
    },
)
async def get_dashboard(
    user: CurrentUser,
    db: DbSession,
) -> DashboardResponse:
    """
    Get complete dashboard statistics.
    
    Returns aggregated metrics for orders, products, customers,
    and recent activity suitable for admin dashboard display.
    """
    logger.info(
        "Dashboard data requested",
        user_id=user.sub,
        user_role=user.role,
    )
    
    dashboard = await dashboard_repository.get_dashboard(db)
    
    logger.info(
        "Dashboard data retrieved",
        user_id=user.sub,
        orders_today=dashboard.orders.today_count,
        products_active=dashboard.products.total_active,
        low_stock=dashboard.products.low_stock_count,
    )
    
    return dashboard

