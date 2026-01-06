"""
Security Utilities
------------------
Password hashing and JWT token management.

Security Decisions:
1. bcrypt for password hashing (slow by design, resistant to GPU attacks)
2. JWT with short expiry + refresh tokens
3. Role claims embedded in token (no DB lookup on every request)
4. Timing-safe comparisons to prevent timing attacks
"""

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from src.core.config import get_settings
from src.core.exceptions import AuthenticationError, SessionExpiredError

settings = get_settings()


# ─────────────────────────────────────────────────────────────────
# Password Hashing
# ─────────────────────────────────────────────────────────────────

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.bcrypt_rounds,
)


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.
    
    Args:
        password: Plain text password
        
    Returns:
        Hashed password string
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    
    Uses timing-safe comparison to prevent timing attacks.
    
    Args:
        plain_password: Plain text password to verify
        hashed_password: Previously hashed password
        
    Returns:
        True if password matches, False otherwise
    """
    return pwd_context.verify(plain_password, hashed_password)


# ─────────────────────────────────────────────────────────────────
# Roles & Permissions
# ─────────────────────────────────────────────────────────────────

class Role(StrEnum):
    """
    User roles in the system.
    
    Hierarchy (highest to lowest):
    - ADMIN: Full system access, user management
    - MANAGER: Inventory adjustments, reports, approvals
    - SUPERVISOR: Stock movements, receiving, audits
    - STAFF: Basic operations, viewing, sales
    
    Role assignments follow principle of least privilege.
    """
    
    ADMIN = "admin"
    MANAGER = "manager"
    SUPERVISOR = "supervisor"
    STAFF = "staff"


# Role hierarchy for permission checking
ROLE_HIERARCHY: dict[Role, int] = {
    Role.ADMIN: 100,
    Role.MANAGER: 75,
    Role.SUPERVISOR: 50,
    Role.STAFF: 25,
}


def has_role_or_higher(user_role: Role, required_role: Role) -> bool:
    """
    Check if user role meets or exceeds required role.
    
    Args:
        user_role: The user's current role
        required_role: Minimum required role for action
        
    Returns:
        True if user has sufficient privileges
    """
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 100)


# ─────────────────────────────────────────────────────────────────
# JWT Tokens
# ─────────────────────────────────────────────────────────────────

class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """JWT token payload structure."""
    
    sub: str  # Subject (user ID)
    role: Role
    type: TokenType
    exp: datetime
    iat: datetime
    jti: str | None = None  # JWT ID for token revocation


def create_access_token(
    user_id: str,
    role: Role,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a short-lived access token.
    
    Args:
        user_id: Unique user identifier
        role: User's role for authorization
        expires_delta: Custom expiry (defaults to config value)
        
    Returns:
        Encoded JWT string
    """
    now = datetime.now(UTC)
    expires = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))
    
    payload = {
        "sub": user_id,
        "role": role.value,
        "type": TokenType.ACCESS.value,
        "exp": expires,
        "iat": now,
    }
    
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str, role: Role) -> str:
    """
    Create a long-lived refresh token.
    
    Refresh tokens:
    - Are stored securely (httpOnly cookie or secure storage)
    - Used only to obtain new access tokens
    - Have longer expiry than access tokens
    """
    now = datetime.now(UTC)
    expires = now + timedelta(days=settings.refresh_token_expire_days)
    
    payload = {
        "sub": user_id,
        "role": role.value,
        "type": TokenType.REFRESH.value,
        "exp": expires,
        "iat": now,
    }
    
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType = TokenType.ACCESS) -> TokenPayload:
    """
    Decode and validate a JWT token.
    
    Args:
        token: Encoded JWT string
        expected_type: Expected token type (access or refresh)
        
    Returns:
        Validated token payload
        
    Raises:
        SessionExpiredError: Token has expired
        AuthenticationError: Token is invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        
        # Verify token type
        if payload.get("type") != expected_type.value:
            raise AuthenticationError("Invalid token type")
        
        return TokenPayload(
            sub=payload["sub"],
            role=Role(payload["role"]),
            type=TokenType(payload["type"]),
            exp=datetime.fromtimestamp(payload["exp"], tz=UTC),
            iat=datetime.fromtimestamp(payload["iat"], tz=UTC),
            jti=payload.get("jti"),
        )
        
    except jwt.ExpiredSignatureError:
        raise SessionExpiredError()
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {e}")


def create_token_pair(user_id: str, role: Role) -> dict[str, str]:
    """
    Create both access and refresh tokens.
    
    Returns:
        Dictionary with 'access_token' and 'refresh_token' keys
    """
    return {
        "access_token": create_access_token(user_id, role),
        "refresh_token": create_refresh_token(user_id, role),
        "token_type": "bearer",
    }

