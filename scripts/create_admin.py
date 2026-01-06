#!/usr/bin/env python3
"""
Create Admin User Script
========================
Creates an admin user with specified credentials.

Usage:
    python scripts/create_admin.py
"""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import select

from src.core.database import async_session_factory
from src.core.security import Role, hash_password
from src.modules.users.models import User


async def create_admin_user():
    """Create admin user with specified credentials."""
    email = "admin@gmail.com"
    password = "admin123"
    full_name = "Admin User"
    
    async with async_session_factory() as session:
        # Check if user already exists
        result = await session.execute(
            select(User).where(User.email == email)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            print(f"User with email '{email}' already exists!")
            print(f"  ID: {existing.id}")
            print(f"  Role: {existing.role}")
            return
        
        # Create new admin user
        user = User(
            id=str(uuid4()),
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            role=Role.ADMIN,
            is_verified=True,
            is_active=True,
        )
        
        session.add(user)
        await session.commit()
        
        print("✅ Admin user created successfully!")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Role: {Role.ADMIN.value}")
        print(f"   ID: {user.id}")


if __name__ == "__main__":
    asyncio.run(create_admin_user())

