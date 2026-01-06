#!/usr/bin/env python3
"""
Seed user data with all roles and invite states.

Usage:
  python scripts/seed_users_data.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.core.security import Role, hash_password
from src.modules.users.models import User


TEST_PASSWORD = "TestPassword123!"

AVATAR_URLS = [
    "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=600&q=60",
    "https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=600&q=60",
    "https://images.unsplash.com/photo-1544723795-3fb6469f5b39?auto=format&fit=crop&w=600&q=60",
]

SEED_USERS = [
    {
        "email": "owner@kinmel-test.local",
        "full_name": "Test Owner (Seed)",
        "role": Role.ADMIN,
        "is_verified": True,
        "phone": "+61 400 100 001",
        "avatar_url": AVATAR_URLS[0],
    },
    {
        "email": "manager@kinmel-test.local",
        "full_name": "Test Manager (Seed)",
        "role": Role.MANAGER,
        "is_verified": True,
        "phone": "+61 400 100 002",
        "avatar_url": AVATAR_URLS[1],
    },
    {
        "email": "supervisor@kinmel-test.local",
        "full_name": "Test Supervisor (Seed)",
        "role": Role.SUPERVISOR,
        "is_verified": True,
        "phone": "+61 400 100 003",
        "avatar_url": AVATAR_URLS[2],
    },
    {
        "email": "staff1@kinmel-test.local",
        "full_name": "Test Staff One (Seed)",
        "role": Role.STAFF,
        "is_verified": True,
        "phone": "+61 400 100 004",
        "avatar_url": AVATAR_URLS[1],
    },
    {
        "email": "invited@kinmel-test.local",
        "full_name": "Invited User (Seed)",
        "role": Role.STAFF,
        "is_verified": False,
        "phone": None,
        "avatar_url": AVATAR_URLS[0],
        "invite_token": "seed-invite-token",
        "invited_at": datetime.now(UTC) - timedelta(days=1),
        "invite_expires_at": datetime.now(UTC) + timedelta(days=2),
    },
    {
        "email": "inactive@kinmel-test.local",
        "full_name": "Inactive User (Seed)",
        "role": Role.STAFF,
        "is_verified": True,
        "phone": "+61 400 100 005",
        "avatar_url": AVATAR_URLS[2],
        "is_active": False,
        "deleted_at": datetime.now(UTC) - timedelta(days=10),
    },
]


async def seed_users() -> None:
    async with async_session_factory() as session:
        created = 0
        for entry in SEED_USERS:
            existing = await session.execute(select(User).where(User.email == entry["email"]))
            if existing.scalar_one_or_none():
                continue
            user = User(
                email=entry["email"],
                password_hash=hash_password(TEST_PASSWORD),
                full_name=entry["full_name"],
                phone=entry.get("phone"),
                avatar_url=entry.get("avatar_url"),
                role=entry["role"],
                is_verified=entry.get("is_verified", True),
                invited_at=entry.get("invited_at"),
                invite_token=entry.get("invite_token"),
                invite_expires_at=entry.get("invite_expires_at"),
                is_active=entry.get("is_active", True),
                deleted_at=entry.get("deleted_at"),
            )
            session.add(user)
            created += 1
        await session.commit()
        print(f"Seeded users: {created}")


def main() -> None:
    asyncio.run(seed_users())


if __name__ == "__main__":
    main()
