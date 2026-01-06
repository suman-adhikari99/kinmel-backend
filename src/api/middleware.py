"""
API Middleware
--------------
Request/response processing middleware.

Middleware Stack (order matters - first added is outermost):
1. Correlation ID - Add request tracing
2. Request Logging - Log request/response
3. Rate Limiting - Prevent abuse
4. Error Handling - Catch unhandled exceptions
"""

import time
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import get_settings
from src.core.logging import get_logger, set_correlation_id

settings = get_settings()
logger = get_logger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Adds correlation ID to every request for distributed tracing.
    
    The correlation ID is:
    1. Extracted from X-Correlation-ID header if present
    2. Generated if not present
    3. Added to response headers
    4. Available in logs via context variable
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid4())
        set_correlation_id(correlation_id)
        
        # Process request
        response = await call_next(request)
        
        # Add to response headers for client-side tracing
        response.headers["X-Correlation-ID"] = correlation_id
        
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs request/response details for observability.
    
    Logs:
    - Request: method, path, client IP
    - Response: status code, duration
    
    Skips health check endpoints to reduce noise.
    """
    
    SKIP_PATHS = {"/health", "/ready", "/metrics", "/docs", "/openapi.json"}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip noisy endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)
        
        # Record start time
        start_time = time.perf_counter()
        
        # Log request
        logger.info(
            "Request started",
            method=request.method,
            path=request.url.path,
            client_ip=request.client.host if request.client else "unknown",
        )
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000
        
        # Log response
        log_method = logger.warning if response.status_code >= 400 else logger.info
        log_method(
            "Request completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        
        # Add timing header for debugging
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting.
    
    For production, use Redis-based rate limiting for distributed deployment.
    This is a basic implementation for development and single-instance deploys.
    
    Rate limiting protects against:
    - Accidental spam (staff clicking buttons rapidly)
    - Brute force attacks
    - Resource exhaustion
    """
    
    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: dict[str, list[float]] = {}
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks
        if request.url.path in {"/health", "/ready"}:
            return await call_next(request)
        # Skip rate limiting for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Get client identifier (IP or user ID if authenticated)
        client_id = request.client.host if request.client else "unknown"
        
        # Check rate limit
        current_time = time.time()
        window_start = current_time - 60  # 1 minute window
        
        # Clean old entries and count recent requests
        if client_id in self.requests:
            self.requests[client_id] = [
                ts for ts in self.requests[client_id] if ts > window_start
            ]
        else:
            self.requests[client_id] = []
        
        # Check if over limit
        if len(self.requests[client_id]) >= self.requests_per_minute:
            logger.warning(
                "Rate limit exceeded",
                client_id=client_id,
                requests_in_window=len(self.requests[client_id]),
            )
            return Response(
                content='{"detail": "Too many requests. Please wait a moment."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )
        
        # Record this request
        self.requests[client_id].append(current_time)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        remaining = self.requests_per_minute - len(self.requests[client_id])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response


def setup_middleware(app: FastAPI) -> None:
    """
    Configure all middleware for the application.
    
    Order matters! Middleware is processed in reverse order of addition.
    """
    
    # Build CORS allowlist (include frontend_base_url and de-duplicate)
    extra_origins = [settings.frontend_base_url] if settings.frontend_base_url else []
    # Always keep local port 3001 handy for dev/front-end preview builds
    dev_preview_origins = ["http://localhost:3001", "http://127.0.0.1:3001"]
    cors_origins = list(
        dict.fromkeys([*settings.allowed_origins, *extra_origins, *dev_preview_origins])
    )
    # In development allow any localhost/127.* port to avoid preflight 400s
    allow_origin_regex = (
        r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$" if settings.is_development else None
    )
    
    # CORS - must be last added (first processed)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Response-Time"],
    )
    
    # Rate limiting
    app.add_middleware(
        RateLimitMiddleware,
        requests_per_minute=settings.rate_limit_requests_per_minute,
    )
    
    # Request logging
    app.add_middleware(RequestLoggingMiddleware)
    
    # Correlation ID - first added (last processed, closest to route)
    app.add_middleware(CorrelationIdMiddleware)
