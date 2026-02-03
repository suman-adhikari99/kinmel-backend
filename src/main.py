"""
Kinmel - Grocery Inventory Management System
=============================================

Application entry point and FastAPI configuration.

Startup Sequence:
1. Load configuration from environment
2. Configure structured logging
3. Initialize database connection pool
4. Register middleware
5. Register exception handlers
6. Mount API routers
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.exception_handlers import setup_exception_handlers
from src.api.middleware import setup_middleware
from src.core.config import get_settings
from src.core.database import close_db, init_db
from src.core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown tasks:
    - Database connection pool
    - Background task workers
    - Cache connections
    """
    # ─────────────────────────────────────────────────────────────
    # Startup
    # ─────────────────────────────────────────────────────────────
    configure_logging()
    logger.info(
        "Starting Kinmel Inventory System",
        environment=settings.app_env,
        debug=settings.debug,
    )
    
    # Initialize database
    await init_db()
    logger.info("Database connection pool initialized")
    
    yield  # Application runs here
    
    # ─────────────────────────────────────────────────────────────
    # Shutdown
    # ─────────────────────────────────────────────────────────────
    logger.info("Shutting down Kinmel Inventory System")
    
    # Close database connections
    await close_db()
    logger.info("Database connections closed")


# ─────────────────────────────────────────────────────────────────
# Application Factory
# ─────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """
    Application factory pattern.
    
    Benefits:
    - Testable (create fresh app for each test)
    - Configurable (different settings per environment)
    - Clear initialization order
    """
    
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        # Docs URLs - available in all environments for now
        # In production, consider putting behind auth or disabling
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
        # Swagger UI customization
        swagger_ui_parameters={
            "docExpansion": "none",
            "filter": True,
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
    )
    
    # Setup middleware (order matters!)
    setup_middleware(app)
    
    # Setup exception handlers
    setup_exception_handlers(app)
    
    # ─────────────────────────────────────────────────────────────
    # Health Check Endpoints
    # ─────────────────────────────────────────────────────────────
    
    @app.get("/health", tags=["Health"])
    async def health_check():
        """
        Basic health check.
        
        Used by load balancers and container orchestrators.
        Returns 200 if the application is running.
        """
        return {"status": "healthy", "service": "kinmel"}
    
    @app.get("/ready", tags=["Health"])
    async def readiness_check():
        """
        Readiness check.
        
        Verifies all dependencies are available:
        - Database connection
        - Redis connection (TODO)
        
        Returns 200 only if ready to serve traffic.
        """
        # TODO: Add actual dependency checks
        return {"status": "ready", "service": "kinmel"}
    
    # ─────────────────────────────────────────────────────────────
    # API Routers
    # ─────────────────────────────────────────────────────────────
    
    from src.modules.auth.router import router as auth_router
    from src.modules.inventory.router import router as inventory_router
    from src.modules.admin.router import router as admin_router
    from src.modules.products.router import router as products_router
    from src.modules.products.router import categories_router
    from src.modules.dashboard.router import router as dashboard_router
    from src.modules.users.router import router as users_router
    from src.modules.orders.router import router as orders_router
    from src.modules.revenue.router import router as revenue_router
    from src.modules.business.router import router as business_router
    from src.modules.reports.router import router as reports_router
    from src.modules.customers.router import router as customers_router
    from src.modules.notifications.router import router as notifications_router
    from src.modules.pos.router import router as pos_router
    
    # Auth router (login, refresh, register)
    app.include_router(
        auth_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    # Users router (profile)
    app.include_router(
        users_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    app.include_router(
        inventory_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    app.include_router(
        admin_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    app.include_router(
        products_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    app.include_router(
        categories_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    app.include_router(
        dashboard_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        orders_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        revenue_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        business_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        reports_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        customers_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        notifications_router,
        prefix=f"{settings.api_v1_prefix}",
    )

    app.include_router(
        pos_router,
        prefix=f"{settings.api_v1_prefix}",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Static Files (for avatar uploads, etc.)
    # ─────────────────────────────────────────────────────────────
    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
    
    # ─────────────────────────────────────────────────────────────
    # Configure OpenAPI Documentation
    # ─────────────────────────────────────────────────────────────
    from src.api.openapi import configure_openapi
    configure_openapi(app)
    
    return app


# Create application instance
app = create_app()
