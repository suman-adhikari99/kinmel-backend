"""
API Dependencies
----------------
FastAPI dependency injection components.

These dependencies are used across routes to:
1. Provide database sessions
2. Extract and validate authentication
3. Enforce role-based access control
4. Add request context (correlation IDs, etc.)
"""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_async_session
from src.core.exceptions import AuthenticationError, AuthorizationError
from src.core.logging import get_correlation_id, set_correlation_id
from src.core.security import Role, TokenPayload, decode_token, has_role_or_higher

# Security scheme for OpenAPI docs
bearer_scheme = HTTPBearer(auto_error=False)


# ─────────────────────────────────────────────────────────────────
# Database Session
# ─────────────────────────────────────────────────────────────────

async def get_db() -> AsyncSession:
    """
    Database session dependency.
    
    Usage:
        @router.get("/items")
        async def get_items(db: DbSession):
            ...
    """
    async for session in get_async_session():
        yield session


# Type alias for cleaner route signatures
DbSession = Annotated[AsyncSession, Depends(get_db)]


# ─────────────────────────────────────────────────────────────────
# Correlation ID
# ─────────────────────────────────────────────────────────────────

async def get_or_create_correlation_id(
    x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
) -> str:
    """
    Extract or generate correlation ID for request tracing.
    
    If client provides X-Correlation-ID header, use it.
    Otherwise, generate a new one.
    """
    from uuid import uuid4
    
    correlation_id = x_correlation_id or str(uuid4())
    set_correlation_id(correlation_id)
    return correlation_id


CorrelationId = Annotated[str, Depends(get_or_create_correlation_id)]


# ─────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str | None = Query(default=None),
) -> TokenPayload:
    """
    Extract and validate current user from JWT token.
    
    Raises:
        HTTPException 401: Missing or invalid token
    """
    raw_token = None
    if credentials:
        raw_token = credentials.credentials
    elif token:
        raw_token = token

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        return decode_token(raw_token)
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=e.staff_message,
            headers={"WWW-Authenticate": "Bearer"},
        )


# Type alias for authenticated routes
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────
# Role-Based Access Control
# ─────────────────────────────────────────────────────────────────

class RequireRole:
    """
    Dependency that enforces minimum role requirement.
    
    Usage:
        @router.post("/adjust-stock")
        async def adjust_stock(
            user: CurrentUser,
            _: Annotated[None, Depends(RequireRole(Role.SUPERVISOR))],
        ):
            ...
    
    Or as a simpler pattern:
        @router.post("/adjust-stock", dependencies=[Depends(RequireRole(Role.SUPERVISOR))])
        async def adjust_stock(user: CurrentUser):
            ...
    """
    
    def __init__(self, minimum_role: Role):
        self.minimum_role = minimum_role
    
    async def __call__(self, user: CurrentUser) -> None:
        if not has_role_or_higher(user.role, self.minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires {self.minimum_role.value} role or higher.",
            )


# Pre-built role dependencies for common access levels
RequireStaff = Depends(RequireRole(Role.STAFF))
RequireSupervisor = Depends(RequireRole(Role.SUPERVISOR))
RequireManager = Depends(RequireRole(Role.MANAGER))
RequireAdmin = Depends(RequireRole(Role.ADMIN))


# ─────────────────────────────────────────────────────────────────
# Optional Authentication
# ─────────────────────────────────────────────────────────────────

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenPayload | None:
    """
    Extract current user if token provided, otherwise return None.
    
    Useful for endpoints that work differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return decode_token(credentials.credentials)
    except AuthenticationError:
        return None


OptionalUser = Annotated[TokenPayload | None, Depends(get_optional_user)]
