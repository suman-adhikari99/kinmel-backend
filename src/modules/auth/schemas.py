"""
Auth Schemas
------------
Pydantic models for authentication requests and responses.
"""

from datetime import datetime
import re

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, field_validator

from src.core.config import get_settings
from src.core.security import Role

settings = get_settings()


def _normalize_email(value: str) -> str:
    """
    Normalize and validate email addresses.
    
    - Uses email-validator for RFC-compliant validation
    - Allows .local domains only in development to support seed/test data
    - Always lowercases the email for consistency
    """
    email = value.strip().lower()
    
    try:
        return validate_email(email, check_deliverability=False).email
    except EmailNotValidError as exc:
        if settings.is_development and email.endswith(".local"):
            local_part, _, domain = email.partition("@")
            if local_part and domain:
                return email
        raise ValueError(str(exc))


class LoginRequest(BaseModel):
    """Login request body."""
    
    email: str
    password: str
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class RegisterRequest(BaseModel):
    """Registration request body for new staff accounts."""
    
    email: str
    password: str  # Min 8 chars, uppercase, lowercase, number required
    full_name: str  # 2-100 characters
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)
    
    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain lowercase letter")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain digit")
        return value
    
    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        name = value.strip()
        if not (2 <= len(name) <= 100):
            raise ValueError("Full name must be between 2 and 100 characters")
        return name


class RegisterResponse(BaseModel):
    """Response payload after successful registration."""
    
    id: str
    email: str
    full_name: str
    role: Role
    is_verified: bool
    is_active: bool
    created_at: datetime
    message: str


class TokenResponse(BaseModel):
    """Token response after successful authentication."""
    
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Refresh token request body."""
    
    refresh_token: str


class RefreshResponse(BaseModel):
    """New access token after refresh."""
    
    access_token: str
    token_type: str = "bearer"


# ─────────────────────────────────────────────────────────────────
# Forgot Password / Reset Password
# ─────────────────────────────────────────────────────────────────


class ForgotPasswordRequest(BaseModel):
    """Request payload for forgot password."""
    
    email: str
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class ForgotPasswordResponse(BaseModel):
    """Response after forgot password request."""
    
    message: str
    email_hint: str
    expires_in_seconds: int
    attempts_used: int
    max_attempts: int


class ResetPasswordRequest(BaseModel):
    """Request payload for password reset with OTP."""
    
    email: str
    otp: str
    new_password: str
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _normalize_email(value)
    
    @field_validator("otp")
    @classmethod
    def validate_otp(cls, value: str) -> str:
        otp = value.strip()
        if not re.match(r"^\d{6}$", otp):
            raise ValueError("OTP must be a 6-digit code")
        return otp
    
    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain uppercase letter")
        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain lowercase letter")
        if not re.search(r"\d", value):
            raise ValueError("Password must contain digit")
        return value


class ResetPasswordResponse(BaseModel):
    """Response after successful password reset."""
    
    message: str

