"""
Test Configuration
------------------
Shared fixtures for all tests.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.core.database import Base, get_async_session
from src.core.security import Role, create_access_token
from src.main import app


# ─────────────────────────────────────────────────────────────────
# Event Loop
# ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ─────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────

# Use SQLite for fast unit tests
# For integration tests, you can still point to a database Testcontainer if needed
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Create a fresh database for each test.
    
    Uses SQLite in-memory for speed.
    For integration tests, switch to a Testcontainers database if needed.
    """
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session
    
    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


# ─────────────────────────────────────────────────────────────────
# HTTP Clients
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Synchronous test client for simple tests."""
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async test client for async tests."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


# ─────────────────────────────────────────────────────────────────
# Authentication Helpers
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def staff_token() -> str:
    """Generate a valid staff token for testing."""
    return create_access_token(user_id="test-staff-1", role=Role.STAFF)


@pytest.fixture
def supervisor_token() -> str:
    """Generate a valid supervisor token for testing."""
    return create_access_token(user_id="test-supervisor-1", role=Role.SUPERVISOR)


@pytest.fixture
def manager_token() -> str:
    """Generate a valid manager token for testing."""
    return create_access_token(user_id="test-manager-1", role=Role.MANAGER)


@pytest.fixture
def admin_token() -> str:
    """Generate a valid admin token for testing."""
    return create_access_token(user_id="test-admin-1", role=Role.ADMIN)


def auth_headers(token: str) -> dict[str, str]:
    """Create authorization headers from a token."""
    return {"Authorization": f"Bearer {token}"}
