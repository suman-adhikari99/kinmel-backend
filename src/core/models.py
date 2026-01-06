"""
Base Model Components
---------------------
Shared model mixins and utilities for all domain models.

Design Principles:
1. Consistency: All models share common fields (id, timestamps)
2. Auditability: Every record tracks creation and modification
3. Safety: Soft deletes preserve history
4. Concurrency: Version field enables optimistic locking
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class TimestampMixin:
    """
    Mixin that adds created_at and updated_at timestamps.
    
    - created_at: Set once on insert, never changes
    - updated_at: Updated on every modification
    
    Both use database server time for consistency across application instances.
    """
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Mixin for soft delete functionality.
    
    Why soft delete?
    - Preserve audit history
    - Allow recovery from mistakes
    - Maintain referential integrity
    
    All queries should filter by is_active=True unless explicitly including deleted records.
    """
    
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
        index=True,
    )
    
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    
    def soft_delete(self) -> None:
        """Mark record as deleted without removing from database."""
        self.is_active = False
        self.deleted_at = datetime.now(UTC)


class VersionedMixin:
    """
    Mixin for optimistic locking via version number.
    
    How it works:
    1. Read record with version N
    2. Attempt update with WHERE version = N
    3. If rows affected = 0, someone else modified it → raise ConcurrencyError
    4. If successful, version becomes N+1
    
    This prevents lost updates in concurrent scenarios without heavy locking.
    """
    
    version: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    
    def increment_version(self) -> None:
        """Increment version for optimistic locking."""
        self.version += 1


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid4())


class BaseModel(Base, TimestampMixin):
    """
    Abstract base for all domain models.
    
    Provides:
    - UUID primary key
    - Created/updated timestamps
    
    Usage:
        class Product(BaseModel):
            __tablename__ = "products"
            name: Mapped[str] = mapped_column(String(255))
    """
    
    __abstract__ = True
    
    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=generate_uuid,
    )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(id={self.id})>"

