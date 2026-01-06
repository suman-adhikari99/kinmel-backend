"""
User Domain Models
------------------
User accounts and authentication.

This is a minimal model for the User entity, referenced by StockMovement
for audit trails. Full user management will be implemented in a later step.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models import BaseModel, SoftDeleteMixin
from src.core.security import Role


class User(BaseModel, SoftDeleteMixin):
    """
    User account for system access.
    
    Attributes:
        email: Unique login identifier
        password_hash: Bcrypt-hashed password
        full_name: Display name
        phone: Contact phone number (optional)
        avatar_url: Profile picture URL (optional)
        role: Authorization role
        is_active: Can user log in?
        is_verified: Has email been verified?
    """
    
    __tablename__ = "users"
    
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        Index("ix_users_email", "email"),
        Index("ix_users_role", "role"),
        Index("ix_users_invite_token", "invite_token"),
    )
    
    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Email address (used for login)",
    )
    
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Bcrypt-hashed password",
    )
    
    full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        doc="User's full name for display",
    )
    
    phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Contact phone number",
    )
    
    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Profile picture URL",
    )
    
    role: Mapped[Role] = mapped_column(
        String(20),
        nullable=False,
        default=Role.STAFF,
        doc="User's role for authorization",
    )
    
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Has email been verified?",
    )

    invited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the invite was sent",
    )

    invite_token: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        doc="Invite token for accept-invite flow",
    )

    invite_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Invite token expiry timestamp",
    )
    
    def __repr__(self) -> str:
        return f"<User(email={self.email}, role={self.role})>"
