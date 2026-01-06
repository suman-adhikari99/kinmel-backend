"""
Auth Router
-----------
Authentication endpoints for login, registration, and password reset.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.core.config import get_settings
from src.core.email import get_email_service
from src.tasks.email_tasks import send_otp_email_task
from src.core.logging import get_logger
from src.core.security import (
    Role,
    TokenType,
    hash_password,
    create_token_pair,
    create_access_token,
    decode_token,
    verify_password,
)
from src.modules.users.models import User
from src.modules.users.otp_service import get_otp_service
from src.modules.auth.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    TokenResponse,
    RefreshRequest,
    RefreshResponse,
)

settings = get_settings()
logger = get_logger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration",
    description="Create a new staff account pending admin verification.",
)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    """
    Create a new staff user account.
    
    - Public endpoint (no authentication)
    - Rejects duplicate emails with a 409 Conflict
    - Stores bcrypt-hashed password
    """
    result = await db.execute(
        select(User).where(
            User.email == request.email,
            User.deleted_at.is_(None),
        )
    )
    existing_user = result.scalar_one_or_none()
    
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "An account with this email already exists",
                "code": "EMAIL_EXISTS",
            },
        )
    
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        role=Role.STAFF,
        is_verified=False,
        is_active=True,
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    return RegisterResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_verified=user.is_verified,
        is_active=user.is_active,
        created_at=user.created_at,
        message="Account created successfully. Please wait for admin verification.",
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User Login",
    description="Authenticate with email and password to receive JWT tokens.",
)
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate user and return access + refresh tokens.
    
    Args:
        request: Login credentials (email, password)
        db: Database session
        
    Returns:
        TokenResponse with access_token and refresh_token
        
    Raises:
        HTTPException 401: Invalid credentials
        HTTPException 403: Account disabled
    """
    # Find user by email
    result = await db.execute(
        select(User).where(
            User.email == request.email,
            User.deleted_at.is_(None),  # Not soft-deleted
        )
    )
    user = result.scalar_one_or_none()
    
    # Verify user exists and password matches
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact an administrator.",
        )
    
    # Create tokens
    tokens = create_token_pair(str(user.id), Role(user.role))
    
    return TokenResponse(**tokens)


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    summary="Refresh Access Token",
    description="Use a valid refresh token to get a new access token.",
)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    """
    Exchange a refresh token for a new access token.
    
    Args:
        request: Refresh token
        db: Database session
        
    Returns:
        New access token
        
    Raises:
        HTTPException 401: Invalid or expired refresh token
    """
    try:
        # Decode and validate refresh token
        payload = decode_token(request.refresh_token, expected_type=TokenType.REFRESH)
        
        # Verify user still exists and is active
        result = await db.execute(
            select(User).where(
                User.id == payload.sub,
                User.deleted_at.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer valid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Create new access token
        access_token = create_access_token(str(user.id), Role(user.role))
        
        return RefreshResponse(access_token=access_token)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─────────────────────────────────────────────────────────────────
# Forgot Password / Reset Password (Public endpoints)
# ─────────────────────────────────────────────────────────────────


def _mask_email(email: str) -> str:
    """Mask email for display (e.g., us***@example.com)."""
    local, domain = email.split("@")
    if len(local) <= 2:
        masked = f"{local[0]}***"
    else:
        masked = f"{local[:2]}***"
    return f"{masked}@{domain}"


@router.post(
    "/forgot-password",
    response_model=ForgotPasswordResponse,
    summary="Forgot Password",
    description="Request a password reset OTP to be sent to your email.",
)
async def forgot_password(
    request: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ForgotPasswordResponse:
    """
    Send password reset OTP to user's email.
    
    Security:
    - Always returns success (prevents email enumeration)
    - Rate limited to 3 requests per email per hour
    - OTP valid for 30 minutes
    - Email sent in background (non-blocking)
    """
    # Look up user (but don't reveal if exists)
    email_lower = request.email.strip().lower()
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email_lower,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    # Default values
    attempts_used = 0
    max_attempts = 10
    
    # Only send OTP if user exists and is active
    if user and user.is_active:
        otp_service = get_otp_service()
        try:
            otp, expires_in, attempts_used, max_attempts = otp_service.generate_reset_otp(user.email)
            
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
                logger.info(
                    "Reset OTP enqueued",
                    email_hint=_mask_email(email_lower),
                    task_id=task.id,
                )
            except Exception as exc:
                logger.error(
                    "Failed to enqueue reset OTP",
                    email_hint=_mask_email(email_lower),
                    error=str(exc),
                )
                
        except ValueError as e:
            # Rate limited - return with max attempts reached
            logger.warning("Forgot password rate limited", email_hint=_mask_email(email_lower))
            attempts_used = max_attempts
    
    else:
        logger.info(
            "Forgot password skipped - user not found or inactive",
            email_hint=_mask_email(email_lower),
        )

    return ForgotPasswordResponse(
        message="If the email exists, a verification code has been sent",
        email_hint=_mask_email(email_lower),
        expires_in_seconds=1800,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
    )


@router.post(
    "/reset-password",
    response_model=ResetPasswordResponse,
    summary="Reset Password",
    description="Reset password using OTP verification.",
)
async def reset_password(
    request: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> ResetPasswordResponse:
    """
    Reset password with OTP verification.
    
    Raises:
        HTTPException 400: Invalid or expired OTP
        HTTPException 422: Password doesn't meet requirements
    """
    # Look up user
    email_lower = request.email.strip().lower()
    result = await db.execute(
        select(User).where(
            func.lower(User.email) == email_lower,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )
    
    # Verify OTP
    otp_service = get_otp_service()
    if not otp_service.verify_reset_otp(email_lower, request.otp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OTP",
        )
    
    # Update password
    user.password_hash = hash_password(request.new_password)
    await db.commit()
    
    logger.info("Password reset successfully", user_id=user.id)
    
    return ResetPasswordResponse(message="Password reset successfully")
