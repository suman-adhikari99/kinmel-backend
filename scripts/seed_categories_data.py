#!/usr/bin/env python3
"""
Seed product categories with images and statuses.

Usage:
  python scripts/seed_categories_data.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.modules.products.models import Category, CategoryStatus


PLACEHOLDER_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
UPLOADS_DIR = Path(PROJECT_ROOT) / "uploads" / "categories"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "category"


SEED_CATEGORIES = [
    {
        "name": "Dairy",
        "description": "Milk, cheese, yogurt, and chilled staples.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 10,
    },
    {
        "name": "Bakery",
        "description": "Fresh bread, pastries, and baked goods.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 9,
    },
    {
        "name": "Produce",
        "description": "Seasonal fruits and vegetables.",
        "status": CategoryStatus.ACTIVE,
        "featured": True,
        "priority": 8,
    },
    {
        "name": "Pantry",
        "description": "Dry goods, grains, and pantry essentials.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 4,
    },
    {
        "name": "Frozen",
        "description": "Frozen meals, desserts, and ice.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 3,
    },
    {
        "name": "Household",
        "description": "Cleaning supplies and home essentials.",
        "status": CategoryStatus.ACTIVE,
        "featured": False,
        "priority": 2,
    },
    {
        "name": "Seasonal",
        "description": "Archived seasonal products.",
        "status": CategoryStatus.ARCHIVED,
        "featured": False,
        "priority": 0,
        "is_active": False,
        "deleted_at": datetime.now(UTC) - timedelta(days=30),
    },
]


async def seed_categories() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    async with async_session_factory() as session:
        created = 0
        for entry in SEED_CATEGORIES:
            existing = await session.execute(
                select(Category).where(Category.name == entry["name"])
            )
            if existing.scalar_one_or_none():
                continue

            image_file = f"seed-category-{_slugify(entry['name'])}.png"
            image_path = UPLOADS_DIR / image_file
            if not image_path.exists():
                image_path.write_bytes(PLACEHOLDER_PNG_BYTES)

            category = Category(
                name=entry["name"],
                description=entry["description"],
                status=entry["status"],
                featured=entry["featured"],
                priority=entry["priority"],
                image_url=f"/uploads/categories/{image_file}",
                image_file=image_file,
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
