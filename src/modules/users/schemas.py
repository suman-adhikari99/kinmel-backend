"""
User Schemas
------------
Pydantic models for user-related requests and responses.
"""

import re
from datetime import datetime

from pydantic import BaseModel, field_validator
from typing import Literal

from src.core.security import Role


class UserProfileResponse(BaseModel):
    """Response payload for current user profile."""

    id: str
    email: str
    full_name: str
    phone: str | None = None
    avatar_url: str | None = None
    role: Role
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────
# Profile Update
# ─────────────────────────────────────────────────────────────────


class UpdateProfileRequest(BaseModel):
    """Request payload for updating user profile."""

    full_name: str | None = None
    phone: str | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not (2 <= len(name) <= 100):
            raise ValueError("Full name must be between 2 and 100 characters")
        return name

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        phone = value.strip()
        if not phone:
            return None
        # Allow digits, spaces, dashes, parentheses, and leading +
        if not re.match(r"^\+?[\d\s\-\(\)]{7,20}$", phone):
            raise ValueError("Invalid phone format")
        return phone


class UpdateProfileResponse(BaseModel):
    """Response payload after profile update."""

    id: str
    email: str
    full_name: str
    phone: str | None = None
    role: Role
    is_active: bool
    is_verified: bool
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────
# Password Change with OTP
# ─────────────────────────────────────────────────────────────────


class RequestOTPRequest(BaseModel):
    """Request payload for OTP generation."""

    current_password: str


class RequestOTPResponse(BaseModel):
    """Response after OTP is sent."""

    message: str
    email_hint: str
    expires_in_seconds: int
    attempts_used: int
    max_attempts: int


class ChangePasswordRequest(BaseModel):
    """Request payload for password change with OTP verification."""

    otp: str
    new_password: str

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


class ChangePasswordResponse(BaseModel):
    """Response after successful password change."""

    message: str


# ─────────────────────────────────────────────────────────────────
# Avatar Upload
# ─────────────────────────────────────────────────────────────────


class AvatarUploadResponse(BaseModel):
    """Response after avatar upload."""

    avatar_url: str


# ─────────────────────────────────────────────────────────────────
# User Management (Admin/Manager)
# ─────────────────────────────────────────────────────────────────

UserRoleKey = Literal["owner", "manager", "staff", "supervisor"]
UserStatusKey = Literal["active", "inactive", "invited", "canceled"]


class UserListItemResponse(BaseModel):
    id: str
    name: str
    email: str
    role: UserRoleKey
    status: UserStatusKey
    last_active_at: datetime | None
    created_at: datetime
    invited_at: datetime | None
    avatar_url: str | None
    initials: str


class UserListMeta(BaseModel):
    page: int
    page_size: int
    total: int


class UserListResponse(BaseModel):
    data: list[UserListItemResponse]
    meta: UserListMeta


class UserSummaryResponse(BaseModel):
    counts: dict[str, int]
    roles: dict[str, int]


class InviteUserRequest(BaseModel):
    name: str
    email: str
    role: UserRoleKey
    note: str | None = None


class InviteUserResponse(BaseModel):
    id: str
    status: UserStatusKey
    invited_at: datetime


class UpdateUserRequest(BaseModel):
    name: str | None = None
    email: str | None = None


class UpdateUserResponse(BaseModel):
    id: str
    updated_at: datetime


class ChangeRoleRequest(BaseModel):
    role: UserRoleKey


class ChangeRoleResponse(BaseModel):
    id: str
    role: UserRoleKey
    updated_at: datetime


class UserStatusResponse(BaseModel):
    id: str
    status: UserStatusKey


class UserRemoveResponse(BaseModel):
    success: bool


class InviteLinkResponse(BaseModel):
    url: str


class InviteVerifyResponse(BaseModel):
    valid: bool
    user_id: str | None = None
    email: str | None = None
    expires_at: datetime | None = None


class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    name: str | None = None


class AcceptInviteResponse(BaseModel):
    id: str
    status: UserStatusKey


class RolesResponse(BaseModel):
    roles: list[dict]
