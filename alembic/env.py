"""
Alembic Environment Configuration
---------------------------------
Async migration support for SQLAlchemy 2.0 + aiosqlite.

Key Features:
1. Async migrations using aiosqlite
2. Imports all models for autogenerate detection
3. Uses project's database settings
4. Supports both online (connected) and offline (SQL script) modes
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from src.core.config import get_settings
from src.core.database import Base

# ─────────────────────────────────────────────────────────────────
# IMPORTANT: Import all models here for autogenerate to detect them
# ─────────────────────────────────────────────────────────────────
# These imports register models with Base.metadata
# Without these, autogenerate won't see the tables

from src.modules.products.models import Product  # noqa: F401
from src.modules.inventory.models import (  # noqa: F401
    InventoryBatch,
    InventoryItem,
    Location,
    StockMovement,
)
from src.modules.users.models import User  # noqa: F401
from src.modules.orders.models import (  # noqa: F401
    Order,
    OrderContactAttempt,
    OrderExportJob,
    OrderItem,
    OrderItemSubstitution,
    OrderStatusHistory,
)
from src.modules.revenue.models import (  # noqa: F401
    BusinessProfile,
    RevenueAdjustment,
    RevenuePayment,
    RevenuePayout,
)

# ─────────────────────────────────────────────────────────────────
# Alembic Config
# ─────────────────────────────────────────────────────────────────

config = context.config
settings = get_settings()

# Set database URL from application settings
# This overrides any sqlalchemy.url in alembic.ini
config.set_main_option("sqlalchemy.url", str(settings.database_url))

# Configure Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────
# Autogenerate Filters
# ─────────────────────────────────────────────────────────────────

def include_object(obj, name, type_, reflected, compare_to):
    """
    Filter objects for autogenerate.
    
    Use this to exclude:
    - Third-party extension tables
    - Test tables
    - Temporary tables
    
    Returns True to include the object, False to skip.
    """
    # Skip alembic's own version table
    if type_ == "table" and name == "alembic_version":
        return False
    
    # Skip any table starting with underscore (internal/temp)
    if type_ == "table" and name.startswith("_"):
        return False
    
    return True


# ─────────────────────────────────────────────────────────────────
# Offline Mode (Generate SQL scripts)
# ─────────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    
    This generates SQL scripts without connecting to the database.
    Useful for:
    - Generating migration SQL for DBA review
    - Environments where direct DB access isn't available
    - CI/CD pipeline SQL generation
    
    Usage: alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Include schema in output for clarity
        include_schemas=False,  # SQLite doesn't support schemas
        # Use our filter
        include_object=include_object,
        # Render CHECK constraints inline
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────
# Online Mode (Connect to database)
# ─────────────────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    """Execute migrations with an active connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # Use our filter
        include_object=include_object,
        # Compare types for more thorough autogenerate
        compare_type=True,
        # Compare server defaults
        compare_server_default=True,
        # Render CHECK constraints properly
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
        # Include schema changes
        include_schemas=False,  # SQLite doesn't support schemas
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """
    Create async engine and run migrations.
    
    Uses NullPool to avoid connection pool management during migrations.
    Migrations are typically short-lived, one-shot operations.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    
    Connects to the database and executes migrations directly.
    This is the normal mode for development and deployment.
    """
    asyncio.run(run_async_migrations())


# ─────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
