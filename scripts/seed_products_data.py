#!/usr/bin/env python3
"""
Seed product data with images and varied statuses.

Usage:
  python scripts/seed_products_data.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.modules.products.models import Product, ProductStatus


PRODUCT_IMAGES = [
    "https://images.unsplash.com/photo-1514996937319-344454492b37?auto=format&fit=crop&w=800&q=60",
    "https://images.unsplash.com/photo-1464965911861-746a04b4bca6?auto=format&fit=crop&w=800&q=60",
    "https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=800&q=60",
    "https://images.unsplash.com/photo-1506806732259-39c2d0268443?auto=format&fit=crop&w=800&q=60",
]

SEED_PRODUCTS = [
    {
        "sku": "MILK-2L-WHOLE",
        "name": "Whole Milk 2L",
        "description": "Full cream milk, rich and smooth.",
        "category": "Dairy",
        "brand": "Farm Fresh",
        "subcategory": "Milk",
        "image_url": PRODUCT_IMAGES[0],
        "unit_price": Decimal("4.99"),
        "cost_price": Decimal("3.10"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.ACTIVE,
        "featured": True,
        "priority": 10,
        "unit_of_measure": "each",
        "pack_size": 1,
        "is_perishable": True,
        "shelf_life_days": 14,
        "requires_cold_storage": True,
    },
    {
        "sku": "BREAD-SOUR-700",
        "name": "Sourdough Bread 700g",
        "description": "Artisan sourdough loaf, baked daily.",
        "category": "Bakery",
        "brand": "Golden Crust",
        "subcategory": "Bread",
        "image_url": PRODUCT_IMAGES[1],
        "unit_price": Decimal("6.50"),
        "cost_price": Decimal("3.80"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.ACTIVE,
        "featured": True,
        "priority": 8,
        "unit_of_measure": "each",
        "pack_size": 1,
        "is_perishable": True,
        "shelf_life_days": 5,
        "requires_cold_storage": False,
    },
    {
        "sku": "APPLE-GALA-1KG",
        "name": "Gala Apples 1kg",
        "description": "Crisp, sweet gala apples.",
        "category": "Produce",
        "brand": "Orchard Select",
        "subcategory": "Fruit",
        "image_url": PRODUCT_IMAGES[2],
        "unit_price": Decimal("5.20"),
        "cost_price": Decimal("2.90"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.ACTIVE,
        "featured": False,
        "priority": 3,
        "unit_of_measure": "kg",
        "pack_size": 1,
        "is_perishable": True,
        "shelf_life_days": 10,
        "requires_cold_storage": True,
    },
    {
        "sku": "PASTA-PENNE-500",
        "name": "Penne Pasta 500g",
        "description": "Durum wheat penne pasta.",
        "category": "Pantry",
        "brand": "Casa Roma",
        "subcategory": "Pasta",
        "image_url": PRODUCT_IMAGES[3],
        "unit_price": Decimal("2.80"),
        "cost_price": Decimal("1.40"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.ACTIVE,
        "featured": False,
        "priority": 2,
        "unit_of_measure": "pack",
        "pack_size": 1,
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
    },
    {
        "sku": "ICECREAM-VAN-1L",
        "name": "Vanilla Ice Cream 1L",
        "description": "Classic vanilla ice cream.",
        "category": "Frozen",
        "brand": "Cool Treats",
        "subcategory": "Dessert",
        "image_url": PRODUCT_IMAGES[0],
        "unit_price": Decimal("7.90"),
        "cost_price": Decimal("4.20"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.DRAFT,
        "featured": False,
        "priority": 1,
        "unit_of_measure": "each",
        "pack_size": 1,
        "is_perishable": True,
        "shelf_life_days": 60,
        "requires_cold_storage": True,
    },
    {
        "sku": "SOAP-LEM-500",
        "name": "Lemon Dish Soap 500ml",
        "description": "Concentrated dish soap with lemon scent.",
        "category": "Household",
        "brand": "BrightClean",
        "subcategory": "Cleaning",
        "image_url": PRODUCT_IMAGES[1],
        "unit_price": Decimal("3.40"),
        "cost_price": Decimal("1.60"),
        "tax_rate": Decimal("0.10"),
        "status": ProductStatus.ARCHIVED,
        "featured": False,
        "priority": 0,
        "unit_of_measure": "each",
        "pack_size": 1,
        "is_perishable": False,
        "shelf_life_days": None,
        "requires_cold_storage": False,
    },
]


async def seed_products() -> None:
    async with async_session_factory() as session:
        created = 0
        now = datetime.now(UTC)
        for idx, entry in enumerate(SEED_PRODUCTS):
            existing = await session.execute(
                select(Product).where(Product.sku == entry["sku"])
            )
            if existing.scalar_one_or_none():
                continue
            product = Product(
                sku=entry["sku"],
                name=entry["name"],
                description=entry["description"],
                category=entry["category"],
                brand=entry["brand"],
                subcategory=entry["subcategory"],
                image_url=entry["image_url"],
                image_file=None,
                unit_price=entry["unit_price"],
                cost_price=entry["cost_price"],
                tax_rate=entry["tax_rate"],
                status=entry["status"],
                featured=entry["featured"],
                priority=entry["priority"],
                unit_of_measure=entry["unit_of_measure"],
                pack_size=entry["pack_size"],
                is_perishable=entry["is_perishable"],
                shelf_life_days=entry["shelf_life_days"],
                requires_cold_storage=entry["requires_cold_storage"],
                created_at=now - timedelta(days=30 - idx),
                updated_at=now - timedelta(days=15 - idx),
            )
            session.add(product)
            created += 1
        await session.commit()
        print(f"Seeded products: {created}")


def main() -> None:
    asyncio.run(seed_products())


if __name__ == "__main__":
    main()
