#!/usr/bin/env python3
"""
Seed product categories with images and statuses.

Usage:
  python scripts/seed_categories_data.py
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
from src.modules.products.models import Category, CategoryStatus


SEED_CATEGORIES = [
    {
        "name": "Dairy",
        "description": "Milk, cheese, yogurt, and chilled staples.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 10,
        "image_url": "https://images.unsplash.com/photo-1484980972926-edee96e0960d?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Bakery",
        "description": "Fresh bread, pastries, and baked goods.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 9,
        "image_url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Produce",
        "description": "Seasonal fruits and vegetables.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 8,
        "image_url": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Pantry",
        "description": "Dry goods, grains, and pantry essentials.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 4,
        "image_url": "https://images.unsplash.com/photo-1490818387583-1baba5e638af?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Frozen",
        "description": "Frozen meals, desserts, and ice.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 3,
        "image_url": "https://images.unsplash.com/photo-1585504198199-20277593b94f?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Household",
        "description": "Cleaning supplies and home essentials.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 2,
        "image_url": "https://images.unsplash.com/photo-1581578731548-c64695cc6952?auto=format&fit=crop&w=800&q=60",
    },
    {
        "name": "Seasonal",
        "description": "Archived seasonal products.",
        "status": CategoryStatus.ARCHIVED,
        "featured": False,
        "priority": 0,
        "image_url": "https://images.unsplash.com/photo-1501004318641-b39e6451bec6?auto=format&fit=crop&w=800&q=60",
        "is_active": False,
        "deleted_at": datetime.now(UTC) - timedelta(days=30),
    },
]


async def seed_categories() -> None:
    async with async_session_factory() as session:
        created = 0
        for entry in SEED_CATEGORIES:
            existing = await session.execute(
                select(Category).where(Category.name == entry["name"])
            )
            if existing.scalar_one_or_none():
                continue
            category = Category(
                name=entry["name"],
                description=entry["description"],
                status=entry["status"],
                featured=entry["featured"],
                priority=entry["priority"],
                image_url=entry["image_url"],
                image_file=None,
                is_active=entry.get("is_active", True),
                deleted_at=entry.get("deleted_at"),
            )
            session.add(category)
            created += 1
        await session.commit()
        print(f"Seeded categories: {created}")


def main() -> None:
    asyncio.run(seed_categories())


if __name__ == "__main__":
    main()
