#!/usr/bin/env python3
"""
Seed notifications data with type and read-state variety.

Usage:
  python scripts/seed_notifications_data.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.core.security import Role, hash_password
from src.modules.notifications.models import Notification, NotificationRead, NotificationType
from src.modules.users.models import User


SEED_NOTIFICATIONS = [
    {
        "slug": "order-new-1001",
        "type": NotificationType.ORDER,
        "title": "New order #1001 received",
        "message": "Pickup order from Alex Morgan is waiting for confirmation.",
        "source_label": "Open order",
        "source_href": "/dashboard/orders",
        "minutes_ago": 12,
        "read_by": ["owner@kinmel-test.local"],
    },
    {
        "slug": "order-ready-1002",
        "type": NotificationType.ORDER,
        "title": "Order #1002 ready for delivery",
        "message": "Driver can now be assigned for the Surry Hills drop.",
        "source_label": "View delivery queue",
        "source_href": "/dashboard/orders",
        "minutes_ago": 45,
        "read_by": ["owner@kinmel-test.local", "manager@kinmel-test.local"],
    },
    {
        "slug": "stock-low-milk",
        "type": NotificationType.STOCK,
        "title": "Low stock: Whole Milk 2L",
        "message": "Stock is below threshold in floor location FLOOR-A1.",
        "source_label": "Review inventory",
        "source_href": "/dashboard/inventory/low-stock",
        "minutes_ago": 95,
        "read_by": ["manager@kinmel-test.local"],
    },
    {
        "slug": "stock-out-bread",
        "type": NotificationType.STOCK,
        "title": "Out of stock: Sourdough Bread 700g",
        "message": "No sellable units remain. Consider replenishment from backroom.",
        "source_label": "Open out-of-stock view",
        "source_href": "/dashboard/inventory/out-of-stock",
        "minutes_ago": 180,
        "read_by": [],
    },
    {
        "slug": "alert-export-failed",
        "type": NotificationType.ALERT,
        "title": "Orders export failed",
        "message": "A scheduled orders export failed and needs manual retry.",
        "source_label": "Open reports",
        "source_href": "/dashboard/reports",
        "minutes_ago": 310,
        "read_by": ["owner@kinmel-test.local", "manager@kinmel-test.local"],
    },
    {
        "slug": "alert-late-delivery",
        "type": NotificationType.ALERT,
        "title": "Delivery SLA warning",
        "message": "Three orders crossed the estimated delivery window in the last hour.",
        "source_label": "Check orders",
        "source_href": "/dashboard/orders",
        "minutes_ago": 420,
        "read_by": [],
    },
    {
        "slug": "success-revenue-export",
        "type": NotificationType.SUCCESS,
        "title": "Revenue report generated",
        "message": "Monthly revenue export is ready for download.",
        "source_label": "Download report",
        "source_href": "/dashboard/reports",
        "minutes_ago": 540,
        "read_by": ["owner@kinmel-test.local"],
    },
    {
        "slug": "success-user-invite",
        "type": NotificationType.SUCCESS,
        "title": "New staff invite accepted",
        "message": "An invited staff member completed account activation.",
        "source_label": "Manage users",
        "source_href": "/dashboard/users",
        "minutes_ago": 900,
        "read_by": ["owner@kinmel-test.local", "manager@kinmel-test.local"],
    },
]


async def ensure_users(session) -> dict[str, User]:
    emails = {
        "owner@kinmel-test.local",
        "manager@kinmel-test.local",
    }
    users = (
        await session.execute(select(User).where(User.email.in_(emails)))
    ).scalars().all()
    users_by_email = {user.email: user for user in users}

    fallback = [
        ("owner@kinmel-test.local", "Seed Owner", Role.ADMIN),
        ("manager@kinmel-test.local", "Seed Manager", Role.MANAGER),
    ]

    for email, full_name, role in fallback:
        if email in users_by_email:
            continue
        user = User(
            email=email,
            password_hash=hash_password("TestPassword123!"),
            full_name=full_name,
            phone=None,
            avatar_url=None,
            role=role,
            is_verified=True,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        users_by_email[email] = user

    return users_by_email


async def seed_notifications() -> None:
    async with async_session_factory() as session:
        users_by_email = await ensure_users(session)
        now = datetime.now(UTC)

        created_notifications = 0
        created_reads = 0

        for entry in SEED_NOTIFICATIONS:
            notification_id = str(uuid5(NAMESPACE_DNS, f"seed-notification-{entry['slug']}"))
            created_at = now - timedelta(minutes=entry["minutes_ago"])

            existing_notification = await session.execute(
                select(Notification).where(Notification.id == notification_id)
            )
            notification = existing_notification.scalar_one_or_none()

            if not notification:
                notification = Notification(
                    id=notification_id,
                    type=entry["type"],
                    title=entry["title"],
                    message=entry["message"],
                    source_label=entry.get("source_label"),
                    source_href=entry.get("source_href"),
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(notification)
                created_notifications += 1

            for email in entry["read_by"]:
                user = users_by_email.get(email)
                if not user:
                    continue
                existing_read = await session.execute(
                    select(NotificationRead).where(
                        NotificationRead.notification_id == notification_id,
                        NotificationRead.user_id == user.id,
                    )
                )
                if existing_read.scalar_one_or_none():
                    continue

                session.add(
                    NotificationRead(
                        notification_id=notification_id,
                        user_id=user.id,
                        read_at=created_at + timedelta(minutes=10),
                        created_at=created_at + timedelta(minutes=10),
                        updated_at=created_at + timedelta(minutes=10),
                    )
                )
                created_reads += 1

        await session.commit()
        print(
            "Seeded notifications: "
            f"{created_notifications} notifications, {created_reads} read records."
        )


def main() -> None:
    asyncio.run(seed_notifications())


if __name__ == "__main__":
    main()
