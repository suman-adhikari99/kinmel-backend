"""
Database Configuration
----------------------
Async SQLAlchemy 2.0 setup with PostgreSQL via asyncpg.

Design Decisions:
1. Async for non-blocking I/O under load
2. Connection pooling for predictable resource usage
3. Session-per-request pattern for clean transaction boundaries
4. Explicit transaction management (no autocommit surprises)
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings

settings = get_settings()


# ─────────────────────────────────────────────────────────────────
# Naming Conventions
# ─────────────────────────────────────────────────────────────────
# Explicit naming conventions for constraints.
# This ensures consistent, predictable constraint names across migrations.
# Alembic uses these to generate deterministic migration scripts.

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# ─────────────────────────────────────────────────────────────────
# Engine Configuration
# ─────────────────────────────────────────────────────────────────

engine = create_async_engine(
    str(settings.database_url),
    
    # Connection Pool Settings
    # ────────────────────────
    # pool_size: Base number of persistent connections
    # max_overflow: Extra connections allowed during peak load
    # pool_timeout: Seconds to wait for a connection before raising error
    # pool_recycle: Recreate connections after N seconds (prevents stale connections)
    pool_size=settings.db_pool_size,
    pool_pre_ping=True,  # Verify connection is alive before using
    max_overflow=settings.db_pool_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=3600,  # Recycle connections every hour
    
    # Echo SQL in development only (never in production - security + noise)
    echo=settings.debug and settings.is_development,
)


# ─────────────────────────────────────────────────────────────────
# Session Factory
# ─────────────────────────────────────────────────────────────────

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep objects usable after commit
    autoflush=False,  # Explicit flushes only - predictable behavior
    autocommit=False,  # Explicit commits only - no surprises
)


# ─────────────────────────────────────────────────────────────────
# Base Model
# ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    
    All models inherit from this to get:
    - Consistent metadata with naming conventions
    - Common table args
    - Shared functionality
    """
    
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ─────────────────────────────────────────────────────────────────
# Session Dependencies
# ─────────────────────────────────────────────────────────────────

async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency that provides a database session.
    
    Usage in FastAPI:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_async_session)):
            ...
    
    Transaction Behavior:
    - Each request gets a fresh session
    - Commit on success (explicit)
    - Rollback on exception (automatic via context manager)
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_transactional_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for explicit transaction control.
    
    Usage in background tasks or complex operations:
        async with get_transactional_session() as session:
            # Multiple operations in single transaction
            await repo.update_stock(session, sku, qty)
            await repo.log_movement(session, movement)
            # Commit happens automatically on exit
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─────────────────────────────────────────────────────────────────
# Lifecycle Hooks
# ─────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """
    Initialize database connection pool.
    Called at application startup.
    
    Note: Does NOT create tables. Use Alembic migrations for that.
    """
    # Verify database connectivity
    async with engine.begin() as conn:
        await conn.run_sync(lambda _: None)  # Simple connectivity check


async def close_db() -> None:
    """
    Close database connection pool.
    Called at application shutdown.
    """
    await engine.dispose()

