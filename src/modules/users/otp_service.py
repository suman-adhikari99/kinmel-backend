"""
OTP Service
-----------
One-time password generation and verification for password changes.

Uses Redis for temporary OTP storage with automatic expiration.
Falls back to in-memory storage in development when Redis is unavailable.
"""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.config import get_settings
from src.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# OTP Configuration
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 1800  # 30 minutes
OTP_RATE_LIMIT_SECONDS = 60  # Minimum time between OTP requests


class InMemoryStore:
    """
    Simple in-memory store with TTL support.
    Used as fallback when Redis is unavailable (development only).
    
    WARNING: Not suitable for production - OTPs lost on restart,
    and doesn't work across multiple server instances.
    """

    def __init__(self):
        self._store: dict[str, tuple[Any, datetime]] = {}

    def _cleanup_expired(self):
        """Remove expired entries."""
        now = datetime.now(UTC)
        expired = [k for k, (_, exp) in self._store.items() if exp <= now]
        for k in expired:
            del self._store[k]

    def setex(self, key: str, ttl_seconds: int, value: Any) -> None:
        """Set a value with expiration."""
        self._cleanup_expired()
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        self._store[key] = (value, expires_at)

    def get(self, key: str) -> bytes | None:
        """Get a value (returns None if expired or missing)."""
        self._cleanup_expired()
        if key not in self._store:
            return None
        value, expires_at = self._store[key]
        if datetime.now(UTC) >= expires_at:
            del self._store[key]
            return None
        # Return as bytes to match Redis behavior
        return value.encode() if isinstance(value, str) else value

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return self.get(key) is not None

    def delete(self, key: str) -> None:
        """Delete a key."""
        self._store.pop(key, None)

    def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds."""
        if key not in self._store:
            return -2
        _, expires_at = self._store[key]
        remaining = (expires_at - datetime.now(UTC)).total_seconds()
        return max(0, int(remaining))


class OTPService:
    """
    Service for OTP generation, storage, and verification.
    
    Uses Redis for production, falls back to in-memory for development.
    """

    def __init__(self):
        self._store = None
        self._use_redis = True

    @property
    def store(self):
        """Lazy store initialization with Redis fallback."""
        if self._store is not None:
            return self._store

        # Try Redis first
        try:
            from redis import Redis
            redis_client = Redis.from_url(str(settings.redis_url))
            redis_client.ping()  # Test connection
            self._store = redis_client
            logger.info("OTP service using Redis")
        except Exception as e:
            if settings.is_development:
                logger.warning(
                    "Redis unavailable, using in-memory OTP storage (dev only)",
                    error=str(e),
                )
                self._store = InMemoryStore()
                self._use_redis = False
            else:
                # In production, Redis is required
                logger.error("Redis connection failed", error=str(e))
                raise

        return self._store

    def _otp_key(self, user_id: str) -> str:
        """Redis key for storing user's OTP."""
        return f"otp:password_change:{user_id}"

    def _attempt_count_key(self, user_id: str) -> str:
        """Redis key for counting OTP attempts per hour."""
        return f"otp:attempts:{user_id}"

    def generate_otp(self, user_id: str) -> tuple[str, int, int, int]:
        """
        Generate and store a new OTP for the user.
        
        Args:
            user_id: The user's ID
            
        Returns:
            Tuple of (otp_code, expires_in_seconds, attempts_used, max_attempts)
            
        Raises:
            ValueError: If rate limited (max 10 requests per hour)
        """
        store = self.store
        max_attempts = 10

        # Check hourly rate limit (max 10 per hour)
        attempt_key = self._attempt_count_key(user_id)
        attempts = store.get(attempt_key)
        current_attempts = int(attempts.decode()) if attempts else 0
        
        if current_attempts >= max_attempts:
            raise ValueError(
                f"Too many attempts ({max_attempts}/{max_attempts} used). Please try again later."
            )

        # Generate secure random 6-digit OTP
        otp = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))

        # Store OTP with expiration
        otp_key = self._otp_key(user_id)
        store.setex(otp_key, OTP_EXPIRY_SECONDS, otp)

        # Increment attempt counter (expires in 1 hour)
        new_attempts = current_attempts + 1
        store.setex(attempt_key, 3600, str(new_attempts))

        logger.info(
            "OTP generated",
            user_id=user_id,
            expires_in=OTP_EXPIRY_SECONDS,
            attempts_used=new_attempts,
            max_attempts=max_attempts,
        )

        return otp, OTP_EXPIRY_SECONDS, new_attempts, max_attempts

    def verify_otp(self, user_id: str, otp: str) -> bool:
        """
        Verify an OTP for the user.
        
        Args:
            user_id: The user's ID
            otp: The OTP code to verify
            
        Returns:
            True if OTP is valid, False otherwise
            
        Note:
            OTP is invalidated after successful verification (one-time use).
        """
        store = self.store
        otp_key = self._otp_key(user_id)
        stored_otp = store.get(otp_key)

        if not stored_otp:
            logger.warning("OTP verification failed: no OTP found", user_id=user_id)
            return False

        if stored_otp.decode() != otp:
            logger.warning("OTP verification failed: mismatch", user_id=user_id)
            return False

        # Invalidate OTP after successful verification
        store.delete(otp_key)

        logger.info("OTP verified successfully", user_id=user_id)
        return True

    def get_remaining_attempts(self, user_id: str) -> int:
        """Get remaining time until rate limit expires."""
        rate_key = self._rate_limit_key(user_id)
        ttl = self.store.ttl(rate_key)
        return max(0, ttl)

    # ─────────────────────────────────────────────────────────────────
    # Password Reset OTP (for forgot password - keyed by email)
    # ─────────────────────────────────────────────────────────────────

    def _reset_otp_key(self, email: str) -> str:
        """Redis key for storing password reset OTP."""
        return f"otp:password_reset:{email.lower()}"

    def _reset_rate_limit_key(self, email: str) -> str:
        """Redis key for rate limiting password reset requests."""
        return f"otp:reset_rate_limit:{email.lower()}"

    def _reset_attempt_count_key(self, email: str) -> str:
        """Redis key for counting reset attempts per hour."""
        return f"otp:reset_attempts:{email.lower()}"

    def generate_reset_otp(self, email: str) -> tuple[str, int, int, int]:
        """
        Generate and store a password reset OTP.
        
        Args:
            email: User's email address
            
        Returns:
            Tuple of (otp_code, expires_in_seconds, attempts_used, max_attempts)
            
        Raises:
            ValueError: If rate limited (max 10 requests per hour)
        """
        store = self.store
        email_lower = email.lower()
        max_attempts = 10

        # Check hourly rate limit (max 10 per hour)
        attempt_key = self._reset_attempt_count_key(email_lower)
        attempts = store.get(attempt_key)
        current_attempts = int(attempts.decode()) if attempts else 0
        
        if current_attempts >= max_attempts:
            raise ValueError(
                f"Too many password reset requests ({max_attempts}/{max_attempts} used). Please try again later."
            )

        # Generate secure random 6-digit OTP
        otp = "".join(secrets.choice("0123456789") for _ in range(OTP_LENGTH))

        # Store OTP with expiration (30 minutes)
        otp_key = self._reset_otp_key(email_lower)
        store.setex(otp_key, OTP_EXPIRY_SECONDS, otp)

        # Increment attempt counter (expires in 1 hour)
        new_attempts = current_attempts + 1
        store.setex(attempt_key, 3600, str(new_attempts))

        logger.info(
            "Password reset OTP generated",
            email_hint=f"{email_lower[:2]}***",
            expires_in=OTP_EXPIRY_SECONDS,
            attempts_used=new_attempts,
            max_attempts=max_attempts,
        )

        return otp, OTP_EXPIRY_SECONDS, new_attempts, max_attempts

    def verify_reset_otp(self, email: str, otp: str) -> bool:
        """
        Verify a password reset OTP.
        
        Args:
            email: User's email address
            otp: The OTP code to verify
            
        Returns:
            True if OTP is valid, False otherwise
        """
        store = self.store
        email_lower = email.lower()
        otp_key = self._reset_otp_key(email_lower)
        stored_otp = store.get(otp_key)

        if not stored_otp:
            logger.warning("Reset OTP verification failed: no OTP found", email_hint=f"{email_lower[:2]}***")
            return False

        if stored_otp.decode() != otp:
            logger.warning("Reset OTP verification failed: mismatch", email_hint=f"{email_lower[:2]}***")
            return False

        # Invalidate OTP after successful verification
        store.delete(otp_key)

        logger.info("Reset OTP verified successfully", email_hint=f"{email_lower[:2]}***")
        return True


# Singleton instance
_otp_service: OTPService | None = None


def get_otp_service() -> OTPService:
    """Get the OTP service instance."""
    global _otp_service
    if _otp_service is None:
        _otp_service = OTPService()
    return _otp_service
