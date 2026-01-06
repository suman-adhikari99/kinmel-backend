"""
API Client Exceptions
---------------------
Custom exceptions for the Kinmel API client.
"""

from typing import Any


class APIError(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, status_code={self.status_code}, code={self.code})"


class AuthenticationError(APIError):
    """Raised when authentication fails (401)."""
    
    def __init__(self, message: str = "Authentication failed", **kwargs):
        super().__init__(message, status_code=401, **kwargs)


class AuthorizationError(APIError):
    """Raised when user lacks permission (403)."""
    
    def __init__(
        self,
        message: str = "Insufficient permissions",
        required_role: str | None = None,
        user_role: str | None = None,
        **kwargs
    ):
        super().__init__(message, status_code=403, **kwargs)
        self.required_role = required_role
        self.user_role = user_role


class NotFoundError(APIError):
    """Raised when a resource is not found (404)."""
    
    def __init__(
        self,
        message: str = "Resource not found",
        resource: str | None = None,
        identifier: str | None = None,
        **kwargs
    ):
        super().__init__(message, status_code=404, **kwargs)
        self.resource = resource
        self.identifier = identifier


class ValidationError(APIError):
    """Raised when request validation fails (422)."""
    
    def __init__(
        self,
        message: str = "Validation error",
        field: str | None = None,
        errors: list[dict] | None = None,
        **kwargs
    ):
        super().__init__(message, status_code=422, **kwargs)
        self.field = field
        self.errors = errors or []


class ConflictError(APIError):
    """Raised when a conflict occurs (409), e.g., concurrent modification."""
    
    def __init__(self, message: str = "Conflict - resource was modified", **kwargs):
        super().__init__(message, status_code=409, **kwargs)


class InsufficientStockError(ValidationError):
    """Raised when there's not enough stock for an operation."""
    
    def __init__(
        self,
        message: str = "Insufficient stock",
        requested: int | None = None,
        available: int | None = None,
        **kwargs
    ):
        super().__init__(message, code="INSUFFICIENT_STOCK", **kwargs)
        self.requested = requested
        self.available = available


class AdjustmentTooLargeError(ValidationError):
    """Raised when a stock adjustment exceeds the threshold."""
    
    def __init__(
        self,
        message: str = "Adjustment too large",
        adjustment: int | None = None,
        threshold_percent: int | None = None,
        **kwargs
    ):
        super().__init__(message, code="ADJUSTMENT_TOO_LARGE", **kwargs)
        self.adjustment = adjustment
        self.threshold_percent = threshold_percent

