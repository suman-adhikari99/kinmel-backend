"""
Structured Logging Configuration
--------------------------------
Uses structlog for JSON-formatted, correlation-ID-aware logging.

Why Structured Logging?
1. Machine-parseable (easy to query in log aggregators)
2. Correlation IDs link related log entries
3. Context is explicit, not buried in message strings
4. Easy to add fields without changing log format
"""

import logging
import sys
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

import structlog

from src.core.config import get_settings

settings = get_settings()

# Context variable for request correlation ID
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one."""
    cid = correlation_id_ctx.get()
    if not cid:
        cid = str(uuid4())
        correlation_id_ctx.set(cid)
    return cid


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID for current context."""
    correlation_id_ctx.set(correlation_id)


def add_correlation_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Processor that adds correlation ID to every log entry."""
    event_dict["correlation_id"] = get_correlation_id()
    return event_dict


def configure_logging() -> None:
    """
    Configure structured logging for the application.
    
    Development: Pretty-printed, colored console output
    Production: JSON-formatted for log aggregators (ELK, CloudWatch, etc.)
    """
    
    # Shared processors for all environments
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]
    
    if settings.is_development:
        # Development: Human-readable output
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]
    else:
        # Production: JSON for log aggregation
        processors = shared_processors + [
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ]
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard library logging to use structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.DEBUG if settings.debug else logging.INFO,
    )
    
    # Quiet noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.DEBUG if settings.debug else logging.WARNING
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger instance.
    
    Usage:
        logger = get_logger(__name__)
        logger.info("Processing order", order_id=123, sku="MILK-001")
    """
    return structlog.get_logger(name)


# Pre-configured loggers for common use cases
class LoggerMixin:
    """
    Mixin that provides a logger to any class.
    
    Usage:
        class InventoryService(LoggerMixin):
            def adjust_stock(self, sku: str, qty: int):
                self.logger.info("Adjusting stock", sku=sku, quantity=qty)
    """
    
    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        return get_logger(self.__class__.__name__)

