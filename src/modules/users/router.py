"""
Users Router
------------
User profile and account management endpoints.
"""

import os
import uuid
from pathlib import Path

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_db
from src.core.config import get_settings
from src.core.email import get_email_service
from src.core.logging import get_logger
from src.core.security import Role, has_role_or_higher, hash_password, verify_password
from src.modules.users.models import User
from src.modules.users.otp_service import get_otp_service
from src.tasks.email_tasks import send_otp_email_task
from src.modules.users.schemas import (
    AvatarUploadResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    ChangeRoleRequest,
    ChangeRoleResponse,
    InviteLinkResponse,
    InviteUserRequest,
    InviteUserResponse,
    InviteVerifyResponse,
    AcceptInviteRequest,
    AcceptInviteResponse,
    RolesResponse,
    RequestOTPRequest,
    RequestOTPResponse,
    UpdateUserRequest,
    UpdateUserResponse,
    UserListMeta,
    UserListResponse,
    UserListItemResponse,
    UpdateProfileRequest,
    UpdateProfileResponse,
    UserRemoveResponse,
    UserProfileResponse,
    UserStatusResponse,
    UserSummaryResponse,
)

settings = get_settings()
logger = get_logger(__name__)

router = APIRouter(
    prefix="/users",
    tags=["Users"],
)

# Avatar upload configuration
AVATAR_DIR = Path("uploads/avatars")
AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5MB
ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}


async def _get_user_or_403(
    user_id: str,
    db: AsyncSession,
) -> User:
    """Fetch user by ID, raise 401/403 if not found or inactive."""
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Please contact an administrator.",
        )

    return user


async def _get_user_any(
    user_id: str,
    db: AsyncSession,
) -> User:
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "User not found", "code": "NOT_FOUND"},
        )
    return user


def _mask_email(email: str) -> str:
    """Mask email for display (e.g., j***@company.com)."""
    local, domain = email.split("@")
    if len(local) <= 1:
        masked = f"{local[0]}***"
    else:
        masked = f"{local[0]}***"
    return f"{masked}@{domain}"


def _role_from_key(key: str) -> Role:
    if key == "owner":
        return Role.ADMIN
    if key == "manager":
        return Role.MANAGER
    if key == "staff":
        return Role.STAFF
    if key == "supervisor":
        return Role.SUPERVISOR
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={
            "detail": "Invalid role",
            "code": "INVALID_ROLE",
            "field_errors": {"role": "Invalid role"},
        },
    )


def _role_to_key(role: Role) -> str:
    if role == Role.ADMIN:
        return "owner"
    if role == Role.MANAGER:
        return "manager"
    if role == Role.SUPERVISOR:
        return "supervisor"
    return "staff"


def _status_from_user(user: User) -> str:
    if not user.is_active:
        if not user.is_verified:
            return "canceled"
        return "inactive"
    if user.is_verified:
        return "active"
    return "invited"


def _initials(name: str) -> str:
    parts = [p for p in name.strip().split() if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0][0].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _invite_expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=settings.invite_token_expiry_days)


async def _require_manager_or_admin(user: CurrentUser) -> None:
    if not has_role_or_higher(user.role, Role.MANAGER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Insufficient permissions",
                "code": "INSUFFICIENT_ROLE",
            },
        )


async def _count_active_admins(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(
            User.role == Role.ADMIN,
            User.is_active == True,
            User.deleted_at.is_(None),
        )
    )
    return int(result.scalar_one() or 0)


# ─────────────────────────────────────────────────────────────────
# GET /me - Get Current User Profile
# ─────────────────────────────────────────────────────────────────


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Get Current User Profile",
    description="Retrieve the authenticated user's profile information.",
)
async def get_current_user_profile(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserProfileResponse:
    """
    Return profile details for the currently authenticated user.

    Raises:
        HTTPException 401: Invalid or expired token
        HTTPException 403: User account is deactivated
    """
    user = await _get_user_or_403(current_user.sub, db)

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        avatar_url=user.avatar_url,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


# ─────────────────────────────────────────────────────────────────
# PUT /me - Update Profile
# ─────────────────────────────────────────────────────────────────


@router.put(
    "/me",
    response_model=UpdateProfileResponse,
    summary="Update Profile",
    description="Update the authenticated user's profile (name, phone).",
)
async def update_profile(
    request: UpdateProfileRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UpdateProfileResponse:
    """
    Update user profile fields.

    Raises:
        HTTPException 401: Invalid or expired token
        HTTPException 403: User account is deactivated
        HTTPException 422: Validation error
    """
    user = await _get_user_or_403(current_user.sub, db)

    # Update fields if provided
    if request.full_name is not None:
        user.full_name = request.full_name

    if request.phone is not None:
        user.phone = request.phone if request.phone else None

    await db.commit()
    await db.refresh(user)

    logger.info("User profile updated", user_id=user.id)

    return UpdateProfileResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        role=user.role,
        is_active=user.is_active,
        is_verified=user.is_verified,
        updated_at=user.updated_at,
    )


# ─────────────────────────────────────────────────────────────────
# POST /me/password/request-otp - Request OTP for Password Change
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/me/password/request-otp",
    response_model=RequestOTPResponse,
    summary="Request Password Change OTP",
    description="Request an OTP to be sent to user's email for password change.",
)
async def request_password_otp(
    request: RequestOTPRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> RequestOTPResponse:
    """
    Verify current password and send OTP to user's email.

    Raises:
        HTTPException 400: Current password is incorrect
        HTTPException 401: Invalid or expired token
        HTTPException 429: Too many attempts (rate limited)
    
    Note: Email is sent in background (non-blocking).
    """
    user = await _get_user_or_403(current_user.sub, db)

    # Verify current password
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    # Generate OTP
    otp_service = get_otp_service()
    try:
        otp, expires_in, attempts_used, max_attempts = otp_service.generate_otp(str(user.id))
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please try again later.",
        )

    # Send OTP via celery (non-blocking)
    try:
        task = send_otp_email_task.apply_async(
            kwargs={
                "to_email": user.email,
                "otp": otp,
                "expires_minutes": expires_in // 60,
            },
            queue="default",
        )
        logger.info("Password change OTP enqueued", user_id=user.id, task_id=task.id)
    except Exception as exc:
        logger.error("Failed to enqueue password change OTP", user_id=user.id, error=str(exc))

    return RequestOTPResponse(
        message="Verification code sent",
        email_hint=_mask_email(user.email),
        expires_in_seconds=expires_in,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
    )


# ─────────────────────────────────────────────────────────────────
# POST /me/password/change - Verify OTP & Change Password
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/me/password/change",
    response_model=ChangePasswordResponse,
    summary="Change Password",
    description="Verify OTP and set a new password.",
)
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ChangePasswordResponse:
    """
    Verify OTP and update user's password.

    Raises:
        HTTPException 400: Invalid OTP or OTP expired
        HTTPException 401: Invalid or expired token
        HTTPException 422: New password doesn't meet requirements
    """
    user = await _get_user_or_403(current_user.sub, db)

    # Verify OTP
    otp_service = get_otp_service()
    if not otp_service.verify_otp(str(user.id), request.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP or OTP has expired",
        )

    # Update password
    user.password_hash = hash_password(request.new_password)

    await db.commit()

    logger.info("Password changed successfully", user_id=user.id)

    return ChangePasswordResponse(message="Password changed successfully")


# ─────────────────────────────────────────────────────────────────
# POST /me/avatar - Upload Avatar
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/me/avatar",
    response_model=AvatarUploadResponse,
    summary="Upload Avatar",
    description="Upload a profile picture (max 5MB, jpg/png/webp).",
)
async def upload_avatar(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    avatar: UploadFile = File(...),
) -> AvatarUploadResponse:
    """
    Upload and save a profile picture.

    Raises:
        HTTPException 400: Invalid file type or size
        HTTPException 401: Invalid or expired token
        HTTPException 403: User account is deactivated
    """
    user = await _get_user_or_403(current_user.sub, db)

    # Validate file type
    if avatar.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_AVATAR_TYPES)}",
        )

    # Read and validate file size
    contents = await avatar.read()
    if len(contents) > AVATAR_MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {AVATAR_MAX_SIZE // (1024 * 1024)}MB",
        )

    # Generate unique filename
    ext = avatar.filename.split(".")[-1] if avatar.filename else "jpg"
    filename = f"{user.id}-{uuid.uuid4().hex[:8]}.{ext}"

    # Ensure upload directory exists
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)

    # Save file
    file_path = AVATAR_DIR / filename
    with open(file_path, "wb") as f:
        f.write(contents)

    # Delete old avatar if exists
    if user.avatar_url:
        old_filename = user.avatar_url.split("/")[-1]
        old_path = AVATAR_DIR / old_filename
        if old_path.exists():
            os.remove(old_path)

    # Update user avatar URL
    # In production, this would be a CDN URL
    avatar_url = f"/uploads/avatars/{filename}"
    user.avatar_url = avatar_url

    await db.commit()

    logger.info("Avatar uploaded", user_id=user.id, avatar_url=avatar_url)

    return AvatarUploadResponse(avatar_url=avatar_url)


# ─────────────────────────────────────────────────────────────────
# User Management (Admin/Manager)
# ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
)
async def list_users(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = Query(None),
    role: str | None = Query(None, pattern="^(owner|manager|staff|supervisor)$"),
    status_filter: str | None = Query(None, alias="status", pattern="^(active|inactive|invited|canceled)$"),
    sort: str | None = Query("created_at", pattern="^(created_at|name|last_active_at)$"),
    order: str | None = Query("desc", pattern="^(asc|desc)$"),
) -> UserListResponse:
    await _require_manager_or_admin(current_user)

    filters = [User.deleted_at.is_(None)]
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            (func.lower(User.full_name).like(pattern)) | (func.lower(User.email).like(pattern))
        )
    if role:
        filters.append(User.role == _role_from_key(role))
    if status_filter == "active":
        filters.append(User.is_active == True)
        filters.append(User.is_verified == True)
    elif status_filter == "inactive":
        filters.append(User.is_active == False)
        filters.append(User.is_verified == True)
    elif status_filter == "invited":
        filters.append(User.is_active == True)
        filters.append(User.is_verified == False)
    elif status_filter == "canceled":
        filters.append(User.is_active == False)
        filters.append(User.is_verified == False)

    sort_map = {
        "created_at": User.created_at,
        "name": User.full_name,
        "last_active_at": User.updated_at,
    }
    sort_col = sort_map.get(sort or "created_at", User.created_at)
    sort_col = sort_col.desc() if order == "desc" else sort_col.asc()

    total = (await db.execute(select(func.count(User.id)).where(*filters))).scalar_one()
    offset = (page - 1) * page_size
    result = await db.execute(
        select(User).where(*filters).order_by(sort_col).limit(page_size).offset(offset)
    )
    users = result.scalars().all()
    data = [
        UserListItemResponse(
            id=str(user.id),
            name=user.full_name,
            email=user.email,
            role=_role_to_key(user.role),
            status=_status_from_user(user),
            last_active_at=None,
            created_at=user.created_at,
            invited_at=user.invited_at,
            avatar_url=user.avatar_url,
            initials=_initials(user.full_name),
        )
        for user in users
    ]
    return UserListResponse(
        data=data,
        meta=UserListMeta(page=page, page_size=page_size, total=int(total)),
    )


@router.get(
    "/summary",
    response_model=UserSummaryResponse,
    summary="User summary",
)
async def user_summary(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserSummaryResponse:
    await _require_manager_or_admin(current_user)

    total_active = (await db.execute(
        select(func.count(User.id)).where(
            User.is_active == True,
            User.is_verified == True,
            User.deleted_at.is_(None),
        )
    )).scalar_one()
    total_inactive = (await db.execute(
        select(func.count(User.id)).where(
            User.is_active == False,
            User.is_verified == True,
            User.deleted_at.is_(None),
        )
    )).scalar_one()
    total_invited = (await db.execute(
        select(func.count(User.id)).where(
            User.is_active == True,
            User.is_verified == False,
            User.deleted_at.is_(None),
        )
    )).scalar_one()

    role_counts = {}
    for role in Role:
        count = (await db.execute(
            select(func.count(User.id)).where(
                User.role == role,
                User.deleted_at.is_(None),
            )
        )).scalar_one()
        role_counts[_role_to_key(role)] = int(count)

    return UserSummaryResponse(
        counts={
            "active": int(total_active),
            "inactive": int(total_inactive),
            "invited": int(total_invited),
        },
        roles=role_counts,
    )


@router.post(
    "/invite",
    response_model=InviteUserResponse,
    summary="Invite user",
    status_code=status.HTTP_201_CREATED,
)
async def invite_user(
    request: InviteUserRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> InviteUserResponse:
    await _require_manager_or_admin(current_user)

    email = request.email.strip().lower()
    existing = (await db.execute(
        select(User).where(func.lower(User.email) == email, User.deleted_at.is_(None))
    )).scalar_one_or_none()
    if existing:
        if not existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "User exists but inactive",
                    "code": "USER_EXISTS_INACTIVE",
                    "field_errors": {"email": "User exists but inactive"},
                },
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "detail": "Email already exists",
                "code": "USER_EXISTS",
                "field_errors": {"email": "Already exists"},
            },
        )

    user = User(
        email=email,
        password_hash=hash_password(str(uuid.uuid4())),
        full_name=request.name.strip(),
        role=_role_from_key(request.role),
        is_active=True,
        is_verified=False,
        invited_at=datetime.now(UTC),
        invite_token=uuid.uuid4().hex,
        invite_expires_at=_invite_expiry(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    email_service = get_email_service()
    base_url = settings.frontend_base_url or (settings.allowed_origins[0] if settings.allowed_origins else "")
    invite_url = f"{base_url}/invite?token={user.invite_token}"
    expires_at = user.invite_expires_at.isoformat()
    invite_body = (
        f"You have been invited to join {settings.app_name} as {request.role}.\n\n"
        f"{request.note or ''}\n\n"
        f"Accept Invite: {invite_url}\n\n"
        f"This invite expires on {expires_at}\n"
    )
    html_body = f"""
    <div>
      <h2>You&apos;ve been invited to join {settings.app_name}</h2>
      <p>An admin has invited you to access the dashboard as {request.role}.</p>
      <p><a href="{invite_url}" style="background:#111;color:#fff;padding:12px 18px;text-decoration:none;border-radius:6px;display:inline-block;">Accept Invite</a></p>
      <p>If the button doesn&apos;t work, copy this link:</p>
      <p>{invite_url}</p>
      <p>This invite expires on {expires_at}</p>
    </div>
    """
    email_service.send_email(
        to_email=user.email,
        subject="You're invited to Kinmel",
        html_body=html_body,
        text_body=invite_body,
    )

    return InviteUserResponse(
        id=str(user.id),
        status="invited",
        invited_at=user.created_at,
    )


@router.patch(
    "/{user_id}",
    response_model=UpdateUserResponse,
    summary="Update user",
)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UpdateUserResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)

    if request.email:
        email = request.email.strip().lower()
        existing = (await db.execute(
            select(User).where(
                func.lower(User.email) == email,
                User.id != user.id,
                User.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": "Email already exists",
                    "code": "USER_EXISTS",
                    "field_errors": {"email": "Already exists"},
                },
            )
        user.email = email
    if request.name:
        user.full_name = request.name.strip()

    await db.commit()
    await db.refresh(user)
    return UpdateUserResponse(id=str(user.id), updated_at=user.updated_at)


@router.patch(
    "/{user_id}/role",
    response_model=ChangeRoleResponse,
    summary="Change user role",
)
async def change_user_role(
    user_id: str,
    request: ChangeRoleRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> ChangeRoleResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)
    new_role = _role_from_key(request.role)

    if user.role == Role.ADMIN and new_role != Role.ADMIN:
        active_admins = await _count_active_admins(db)
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "Cannot remove last owner", "code": "LAST_OWNER"},
            )

    if new_role == Role.ADMIN and current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"detail": "Only owner can assign owner role", "code": "OWNER_ONLY"},
        )

    user.role = new_role
    await db.commit()
    await db.refresh(user)
    return ChangeRoleResponse(id=str(user.id), role=_role_to_key(user.role), updated_at=user.updated_at)


@router.post(
    "/{user_id}/deactivate",
    response_model=UserStatusResponse,
    summary="Deactivate user",
)
async def deactivate_user(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatusResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)

    if user.role == Role.ADMIN:
        active_admins = await _count_active_admins(db)
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "Cannot deactivate last owner", "code": "LAST_OWNER"},
            )

    user.is_active = False
    await db.commit()
    return UserStatusResponse(id=str(user.id), status="inactive")


@router.post(
    "/{user_id}/reactivate",
    response_model=UserStatusResponse,
    summary="Reactivate user",
)
async def reactivate_user(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatusResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)
    user.is_active = True
    await db.commit()
    return UserStatusResponse(id=str(user.id), status=_status_from_user(user))


@router.post(
    "/{user_id}/resend-invite",
    response_model=InviteUserResponse,
    summary="Resend invite",
)
async def resend_invite(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> InviteUserResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)
    if user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "User already active", "code": "ALREADY_ACTIVE"},
        )

    user.invited_at = datetime.now(UTC)
    user.invite_token = uuid.uuid4().hex
    user.invite_expires_at = _invite_expiry()
    await db.commit()

    email_service = get_email_service()
    base_url = settings.frontend_base_url or (settings.allowed_origins[0] if settings.allowed_origins else "")
    invite_url = f"{base_url}/invite?token={user.invite_token}"
    expires_at = user.invite_expires_at.isoformat()
    html_body = f"""
    <div>
      <h2>You&apos;ve been invited to join {settings.app_name}</h2>
      <p>An admin has invited you to access the dashboard as {_role_to_key(user.role)}.</p>
      <p><a href="{invite_url}" style="background:#111;color:#fff;padding:12px 18px;text-decoration:none;border-radius:6px;display:inline-block;">Accept Invite</a></p>
      <p>If the button doesn&apos;t work, copy this link:</p>
      <p>{invite_url}</p>
      <p>This invite expires on {expires_at}</p>
    </div>
    """
    email_service.send_email(
        to_email=user.email,
        subject="Your Kinmel invite",
        html_body=html_body,
        text_body=f"You have been invited to join {settings.app_name}. Accept: {invite_url}",
    )
    return InviteUserResponse(id=str(user.id), status="invited", invited_at=user.invited_at or datetime.now(UTC))


@router.post(
    "/{user_id}/cancel-invite",
    response_model=UserStatusResponse,
    summary="Cancel invite",
)
async def cancel_invite(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserStatusResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)
    user.is_active = False
    user.is_verified = False
    user.invite_token = None
    user.invite_expires_at = None
    await db.commit()
    return UserStatusResponse(id=str(user.id), status="canceled")


@router.delete(
    "/{user_id}",
    response_model=UserRemoveResponse,
    summary="Remove user",
)
async def remove_user(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> UserRemoveResponse:
    await _require_manager_or_admin(current_user)
    if user_id == current_user.sub:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Cannot remove yourself", "code": "SELF_REMOVE"},
        )
    user = await _get_user_any(user_id, db)
    if user.role == Role.ADMIN:
        active_admins = await _count_active_admins(db)
        if active_admins <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "Cannot remove last owner", "code": "LAST_OWNER"},
            )
    user.is_active = False
    user.deleted_at = datetime.now(UTC)
    await db.commit()
    return UserRemoveResponse(success=True)


@router.get(
    "/{user_id}/invite-link",
    response_model=InviteLinkResponse,
    summary="Invite link",
)
async def invite_link(
    user_id: str,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
) -> InviteLinkResponse:
    await _require_manager_or_admin(current_user)
    user = await _get_user_any(user_id, db)
    if not user.invite_token or (user.invite_expires_at and user.invite_expires_at < datetime.now(UTC)):
        user.invite_token = uuid.uuid4().hex
        user.invite_expires_at = _invite_expiry()
        user.invited_at = user.invited_at or datetime.now(UTC)
        await db.commit()
    base_url = settings.frontend_base_url or (settings.allowed_origins[0] if settings.allowed_origins else "https://dashboard.example.com")
    return InviteLinkResponse(url=f"{base_url}/invite?token={user.invite_token}")


@router.get(
    "/invite/verify",
    response_model=InviteVerifyResponse,
    summary="Verify invite token",
)
async def verify_invite(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> InviteVerifyResponse:
    user = (
        await db.execute(
            select(User).where(
                User.invite_token == token,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Invite not found", "code": "INVITE_NOT_FOUND"},
        )
    if user.invite_expires_at and user.invite_expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"detail": "Invite expired", "code": "INVITE_EXPIRED"},
        )
    return InviteVerifyResponse(
        valid=True,
        user_id=str(user.id),
        email=user.email,
        expires_at=user.invite_expires_at,
    )


@router.post(
    "/invite/accept",
    response_model=AcceptInviteResponse,
    summary="Accept invite",
)
async def accept_invite(
    request: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
) -> AcceptInviteResponse:
    user = (
        await db.execute(
            select(User).where(
                User.invite_token == request.token,
                User.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Invite not found", "code": "INVITE_NOT_FOUND"},
        )
    if user.invite_expires_at and user.invite_expires_at < datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"detail": "Invite expired", "code": "INVITE_EXPIRED"},
        )
    if request.name:
        user.full_name = request.name.strip()
    user.password_hash = hash_password(request.password)
    user.is_verified = True
    user.is_active = True
    user.invite_token = None
    user.invite_expires_at = None
    await db.commit()
    return AcceptInviteResponse(id=str(user.id), status=_status_from_user(user))


@router.get(
    "/audit",
    summary="User audit log",
)
async def user_audit_log(
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    await _require_manager_or_admin(current_user)
    return {
        "data": [],
        "meta": {"page": page, "page_size": page_size, "total": 0},
    }


@router.get(
    "/roles",
    response_model=RolesResponse,
    summary="Roles and permissions",
)
async def list_roles(
    current_user: CurrentUser,
) -> RolesResponse:
    await _require_manager_or_admin(current_user)
    return RolesResponse(
        roles=[
            {"key": "owner", "label": "Owner", "permissions": ["*"]},
            {"key": "manager", "label": "Manager", "permissions": ["orders.read", "orders.update", "inventory.update"]},
            {"key": "supervisor", "label": "Supervisor", "permissions": ["orders.read", "inventory.update"]},
            {"key": "staff", "label": "Staff", "permissions": ["orders.read", "inventory.update"]},
        ]
    )
