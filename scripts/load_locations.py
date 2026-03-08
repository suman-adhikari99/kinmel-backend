#!/usr/bin/env python3
"""
Load default inventory locations for POS.

Usage:
  python scripts/load_locations.py
"""

from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.modules.inventory.models import Location, LocationType


DEFAULT_LOCATIONS = [
    ("LIDCOMBE", "Lidcombe Floor", LocationType.FLOOR),
    ("BACKROOM-01", "Backroom", LocationType.BACKROOM),
    ("COLD-01", "Cold Storage", LocationType.COLD_STORAGE),
]


async def load_locations() -> int:
    async with async_session_factory() as session:
        existing = set((await session.execute(select(Location.code))).scalars().all())
        created = 0
        for code, name, location_type in DEFAULT_LOCATIONS:
            if code in existing:
                continue
            session.add(
                Location(
                    code=code,
                    name=name,
                    location_type=location_type,
                    capacity=None,
                    temperature_zone=None,
                    notes="Seeded location",
                )
            )
            created += 1
        await session.commit()
        return created


def main() -> None:
    created = asyncio.run(load_locations())
    print(f"Locations created: {created}")


if __name__ == "__main__":
    main()
