"""
Exception Handlers
------------------
Centralized exception handling for consistent API responses.

Design Principles:
1. Staff-friendly error messages (no stack traces in responses)
2. Detailed logging for debugging
3. Consistent response format
4. Appropriate HTTP status codes
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from src.core.exceptions import (
    AlreadyExistsError,
    AuthenticationError,
    AuthorizationError,
    ConcurrencyError,
    ExpiredProductError,
    InsufficientStockError,
    KinmelException,
    LocationCapacityExceededError,
    NotFoundError,
    ServiceUnavailableError,
    StockAdjustmentTooLargeError,
)
from src.core.logging import get_correlation_id, get_logger

logger = get_logger(__name__)


def create_error_response(
    status_code: int,
    message: str,
    error_code: str | None = None,
    details: dict | None = None,
) -> JSONResponse:
    """
    Create a consistent error response.
    
    Response Format:
    {
        "error": {
            "message": "Human-readable message",
            "code": "MACHINE_READABLE_CODE",
            "correlation_id": "uuid for support tickets",
            "details": { ... optional extra info ... }
        }
    }
    """
    content = {
        "error": {
            "message": message,
            "correlation_id": get_correlation_id(),
        }
    }
    
    if error_code:
        content["error"]["code"] = error_code
    
    if details:
        content["error"]["details"] = details
    
    return JSONResponse(status_code=status_code, content=content)


async def kinmel_exception_handler(request: Request, exc: KinmelException) -> JSONResponse:
    """Handle all domain exceptions."""
    
    # Log the full exception for debugging
    logger.error(
        "Domain exception",
        exception_type=type(exc).__name__,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    
    # Map exception types to HTTP status codes
    status_map = {
        AuthenticationError: 401,
        AuthorizationError: 403,
        NotFoundError: 404,
        AlreadyExistsError: 409,
        ConcurrencyError: 409,
        InsufficientStockError: 422,
        StockAdjustmentTooLargeError: 422,
        ExpiredProductError: 422,
        LocationCapacityExceededError: 422,
        ServiceUnavailableError: 503,
    }
    
    status_code = status_map.get(type(exc), 500)
    error_code = type(exc).__name__.upper().replace("ERROR", "")
    
    return create_error_response(
        status_code=status_code,
        message=exc.staff_message,
        error_code=error_code,
        details=exc.details if exc.details else None,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic validation errors.
    
    Transforms technical validation errors into staff-friendly messages.
    """
    
    # Extract field-specific errors
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        errors.append({"field": field, "message": message})
    
    logger.warning(
        "Validation error",
        path=request.url.path,
        errors=errors,
    )
    
    # Create user-friendly message
    if len(errors) == 1:
        message = f"Invalid input: {errors[0]['message']}"
    else:
        message = f"Multiple input errors ({len(errors)} fields)"
    
    return create_error_response(
        status_code=422,
        message=message,
        error_code="VALIDATION_ERROR",
        details={"errors": errors},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for unexpected exceptions.
    
    These are bugs - log everything for debugging but show generic message to staff.
    """
    
    logger.exception(
        "Unhandled exception",
        exception_type=type(exc).__name__,
        message=str(exc),
        path=request.url.path,
    )
    
    return create_error_response(
        status_code=500,
        message="An unexpected error occurred. Please try again or contact support.",
        error_code="INTERNAL_ERROR",
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers."""
    
    # Domain exceptions
    app.add_exception_handler(KinmelException, kinmel_exception_handler)
    
    # Validation errors
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    
    # Catch-all for unexpected errors
    app.add_exception_handler(Exception, generic_exception_handler)

