"""
Domain Exceptions
-----------------
Structured exceptions that map to HTTP responses.

Design Principles:
1. Domain exceptions are business-language, not HTTP-language
2. Exception handlers translate to HTTP at the API boundary
3. All exceptions carry enough context for debugging
4. Staff-facing messages are separate from technical details
"""

from typing import Any


class KinmelException(Exception):
    """
    Base exception for all application errors.
    
    Attributes:
        message: Technical message for logs
        staff_message: Human-friendly message for staff UI
        details: Additional context for debugging
    """
    
    def __init__(
        self,
        message: str,
        staff_message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        self.message = message
        self.staff_message = staff_message or "An error occurred. Please try again."
        self.details = details or {}
        super().__init__(self.message)


# ─────────────────────────────────────────────────────────────────
# Authentication & Authorization Exceptions
# ─────────────────────────────────────────────────────────────────

class AuthenticationError(KinmelException):
    """User is not authenticated (401)."""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            staff_message="Please log in to continue.",
        )


class AuthorizationError(KinmelException):
    """User lacks required permissions (403)."""
    
    def __init__(self, required_role: str, action: str):
        super().__init__(
            message=f"Role '{required_role}' required for action '{action}'",
            staff_message="You don't have permission for this action. Contact your manager.",
            details={"required_role": required_role, "action": action},
        )


class SessionExpiredError(AuthenticationError):
    """User session has expired."""
    
    def __init__(self):
        super().__init__(message="Session expired")
        self.staff_message = "Your session has expired. Please log in again."


# ─────────────────────────────────────────────────────────────────
# Resource Exceptions
# ─────────────────────────────────────────────────────────────────

class NotFoundError(KinmelException):
    """Resource not found (404)."""
    
    def __init__(
        self,
        resource: str | None = None,
        identifier: Any | None = None,
        *,
        staff_message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        if staff_message is not None or details is not None:
            message = staff_message or "Resource not found"
            if details is None:
                details = {}
                if resource is not None:
                    details["resource"] = resource
                if identifier is not None:
                    details["identifier"] = str(identifier)
            super().__init__(
                message=message,
                staff_message=message,
                details=details,
            )
            return
        if resource is None:
            super().__init__(
                message="Resource not found",
                staff_message="Could not find the requested resource.",
                details={},
            )
            return
        super().__init__(
            message=f"{resource} not found: {identifier}",
            staff_message=f"Could not find the {resource.lower()}. It may have been deleted.",
            details={"resource": resource, "identifier": str(identifier)},
        )


class AlreadyExistsError(KinmelException):
    """Resource already exists (409)."""
    
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} already exists: {identifier}",
            staff_message=f"This {resource.lower()} already exists.",
            details={"resource": resource, "identifier": str(identifier)},
        )


# ─────────────────────────────────────────────────────────────────
# Inventory-Specific Exceptions
# ─────────────────────────────────────────────────────────────────

class InsufficientStockError(KinmelException):
    """Not enough stock for operation (422)."""
    
    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(
            message=f"Insufficient stock for {sku}: requested {requested}, available {available}",
            staff_message=f"Not enough stock. Only {available} units available.",
            details={
                "sku": sku,
                "requested": requested,
                "available": available,
                "shortage": requested - available,
            },
        )


class StockAdjustmentTooLargeError(KinmelException):
    """
    Stock adjustment exceeds safety threshold (422).
    
    Prevents accidental large adjustments (e.g., typos like 1000 instead of 10).
    Large adjustments require manager approval.
    """
    
    def __init__(self, sku: str, adjustment: int, threshold_percent: int):
        super().__init__(
            message=f"Adjustment {adjustment} exceeds {threshold_percent}% threshold for {sku}",
            staff_message=(
                f"This adjustment is unusually large ({adjustment} units). "
                "Please verify the amount or request manager approval."
            ),
            details={
                "sku": sku,
                "adjustment": adjustment,
                "threshold_percent": threshold_percent,
            },
        )


class ExpiredProductError(KinmelException):
    """Operation on expired product (422)."""
    
    def __init__(self, sku: str, expiry_date: str):
        super().__init__(
            message=f"Product {sku} expired on {expiry_date}",
            staff_message="This product has expired and cannot be sold. Mark it for disposal.",
            details={"sku": sku, "expiry_date": expiry_date},
        )


class LocationCapacityExceededError(KinmelException):
    """Storage location is at capacity (422)."""
    
    def __init__(self, location: str, capacity: int, requested: int):
        super().__init__(
            message=f"Location {location} capacity exceeded: {requested}/{capacity}",
            staff_message=f"This storage location is full. Maximum capacity is {capacity} units.",
            details={
                "location": location,
                "capacity": capacity,
                "requested": requested,
            },
        )


# ─────────────────────────────────────────────────────────────────
# Validation Exceptions
# ─────────────────────────────────────────────────────────────────

class ValidationError(KinmelException):
    """Input validation failed (422)."""
    
    def __init__(
        self,
        field: str | None = None,
        message: str | None = None,
        *,
        staff_message: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        if staff_message is not None or details is not None:
            resolved_message = staff_message or message or "Validation error"
            if details is None:
                details = {}
                if field is not None:
                    details["field"] = field
            super().__init__(
                message=resolved_message,
                staff_message=resolved_message,
                details=details,
            )
            return
        if field is None:
            resolved_message = message or "Validation error"
            super().__init__(
                message=resolved_message,
                staff_message=resolved_message,
                details={},
            )
            return
        super().__init__(
            message=f"Validation failed for '{field}': {message}",
            staff_message=message or "Validation error",
            details={"field": field},
        )


# ─────────────────────────────────────────────────────────────────
# System Exceptions
# ─────────────────────────────────────────────────────────────────

class ServiceUnavailableError(KinmelException):
    """External service or dependency unavailable (503)."""
    
    def __init__(self, service: str):
        super().__init__(
            message=f"Service unavailable: {service}",
            staff_message="System is temporarily busy. Please try again in a moment.",
            details={"service": service},
        )


class ConcurrencyError(KinmelException):
    """
    Concurrent modification detected (409).
    
    Happens when two staff members modify the same resource simultaneously.
    """
    
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"Concurrent modification of {resource}: {identifier}",
            staff_message="Someone else just updated this. Please refresh and try again.",
            details={"resource": resource, "identifier": str(identifier)},
        )
