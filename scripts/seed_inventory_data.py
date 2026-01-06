"""
Seed inventory data for testing.

Creates:
- Default locations (if none exist)
- Inventory items for existing products
- Optional batches for perishable products
"""

from __future__ import annotations

import os
import sys

import asyncio
import random
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.core.security import Role, hash_password
from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.products.models import Category, Product, ProductStatus
from src.modules.users.models import User


TARGET_ITEMS = 250

DEFAULT_LOCATIONS = [
    ("FLOOR-A1", "Floor A1", LocationType.FLOOR),
    ("BACK-01", "Backroom 01", LocationType.BACKROOM),
    ("COLD-01", "Cold Storage 01", LocationType.COLD_STORAGE),
]

CATEGORY_FALLBACKS = [
    "Rice & Grains",
    "Spices & Masalas",
    "Beverages",
    "Snacks",
    "Household",
    "Dairy",
    "Bakery",
]


async def ensure_locations(session) -> list[Location]:
    existing = (await session.execute(select(Location))).scalars().all()
    if existing:
        return existing

    locations = []
    for code, name, location_type in DEFAULT_LOCATIONS:
        location = Location(
            code=code,
            name=name,
            location_type=location_type,
            capacity=None,
            temperature_zone=None,
            notes="Seeded location",
        )
        session.add(location)
        locations.append(location)
    await session.flush()
    return locations


async def seed_inventory() -> None:
    random.seed(42)
    async with async_session_factory() as session:
        locations = await ensure_locations(session)
        if not locations:
            print("No locations available; aborting.")
            return

        categories = (await session.execute(select(Category))).scalars().all()
        category_names = [category.name for category in categories] or CATEGORY_FALLBACKS

        products = (await session.execute(select(Product))).scalars().all()

        existing = (
            await session.execute(
                select(InventoryItem.product_id, InventoryItem.location_id)
            )
        ).all()
        existing_pairs = {(row[0], row[1]) for row in existing}
        existing_count = len(existing_pairs)

        if not products:
            print("No products found; creating seed products.")
        needed_items = max(0, TARGET_ITEMS - existing_count)

        created_items = 0
        created_batches = 0

        for product in products:
            location = random.choice(locations)
            key = (product.id, location.id)
            if key in existing_pairs:
                continue
            stock = random.randint(0, 120)
            reorder_point = random.randint(5, 30)
            buffer = random.randint(0, 5)
            item = InventoryItem(
                product_id=product.id,
                location_id=location.id,
                physical_stock=stock,
                buffer=buffer,
                reorder_point=reorder_point,
                max_stock=stock + random.randint(20, 200),
            )
            session.add(item)
            await session.flush()
            created_items += 1
            existing_pairs.add(key)

            if product.is_perishable and stock > 0:
                batch_qty = max(1, stock // 2)
                expiry = datetime.now(UTC) + timedelta(days=random.randint(3, 30))
                batch = InventoryBatch(
                    inventory_item_id=item.id,
                    quantity=batch_qty,
                    batch_number=f"SEED-{product.sku}",
                    expiry_date=expiry,
                    cost_per_unit=product.cost_price,
                    received_date=datetime.now(UTC),
                )
                session.add(batch)
                created_batches += 1
                created_batches += await seed_expired_batch(session, item, product)

        if needed_items > 0:
            for idx in range(needed_items):
                sku = f"SEED-INV-{existing_count + idx + 1:04d}"
                name = f"Seed Inventory Product {existing_count + idx + 1}"
                category = random.choice(category_names)
                unit_price = round(random.uniform(2.5, 50.0), 2)
                cost_price = round(unit_price * random.uniform(0.4, 0.8), 2)
                is_perishable = random.choice([True, False, False])
                shelf_life = random.randint(5, 60) if is_perishable else None
                product = Product(
                    sku=sku,
                    name=name,
                    description="Seeded inventory product",
                    category=category,
                    brand="SeedBrand",
                    subcategory=None,
                    unit_price=unit_price,
                    cost_price=cost_price,
                    tax_rate=0.1,
                    status=ProductStatus.ACTIVE,
                    featured=False,
                    priority=0,
                    unit_of_measure=random.choice(["each", "kg", "liter", "pack"]),
                    pack_size=random.choice([1, 2, 4, 6]),
                    is_perishable=is_perishable,
                    shelf_life_days=shelf_life,
                    requires_cold_storage=is_perishable,
                )
                session.add(product)
                await session.flush()

                location = random.choice(locations)
                stock = random.randint(0, 120)
                reorder_point = random.randint(5, 30)
                buffer = random.randint(0, 5)
                item = InventoryItem(
                    product_id=product.id,
                    location_id=location.id,
                    physical_stock=stock,
                    buffer=buffer,
                    reorder_point=reorder_point,
                    max_stock=stock + random.randint(20, 200),
                )
                session.add(item)
                await session.flush()
                created_items += 1

                if product.is_perishable and stock > 0:
                    batch_qty = max(1, stock // 2)
                    expiry = datetime.now(UTC) + timedelta(days=random.randint(3, 30))
                    batch = InventoryBatch(
                        inventory_item_id=item.id,
                        quantity=batch_qty,
                        batch_number=f"SEED-{product.sku}",
                        expiry_date=expiry,
                        cost_per_unit=product.cost_price,
                        received_date=datetime.now(UTC),
                    )
                    session.add(batch)
                    created_batches += 1
                    created_batches += await seed_expired_batch(session, item, product)

        created_movements = await seed_movements(session)
        await session.commit()
        print(
            "Seeded inventory: "
            f"{created_items} items, {created_batches} batches, {created_movements} movements."
        )


async def seed_expired_batch(
    session,
    item: InventoryItem,
    product: Product,
) -> int:
    expired_batch_number = f"SEED-EXPIRED-{product.sku}"
    existing = await session.execute(
        select(InventoryBatch.id).where(
            InventoryBatch.inventory_item_id == item.id,
            InventoryBatch.batch_number == expired_batch_number,
        )
    )
    if existing.scalar_one_or_none():
        return 0
    expired_batch = InventoryBatch(
        inventory_item_id=item.id,
        quantity=max(1, int(item.physical_stock / 4)),
        batch_number=expired_batch_number,
        expiry_date=datetime.now(UTC) - timedelta(days=2),
        received_date=datetime.now(UTC) - timedelta(days=15),
        cost_per_unit=product.cost_price,
    )
    session.add(expired_batch)
    return 1


async def seed_movements(session) -> int:
    items = (await session.execute(select(InventoryItem))).scalars().all()
    if not items:
        return 0
    item = items[0]
    now = datetime.now(UTC)

    user = (
        await session.execute(select(User).where(User.email == "inventory-bot@kinmel-test.local"))
    ).scalar_one_or_none()
    if not user:
        user = User(
            email="inventory-bot@kinmel-test.local",
            password_hash=hash_password("TestPassword123!"),
            full_name="Inventory Bot (Seed)",
            phone=None,
            avatar_url=None,
            role=Role.MANAGER,
            is_verified=True,
        )
        session.add(user)
        await session.flush()

    movements = [
        (MovementType.RECEIVING, MovementReason.SUPPLIER_DELIVERY, 20, "Supplier delivery"),
        (MovementType.SALE, MovementReason.CUSTOMER_SALE, -5, "Point of sale"),
        (MovementType.TRANSFER, MovementReason.INTERNAL_TRANSFER, -3, "Transfer to backroom"),
        (MovementType.ADJUSTMENT, MovementReason.CYCLE_COUNT, 2, "Cycle count adjustment"),
        (MovementType.RETURN, MovementReason.CUSTOMER_RETURN, 1, "Customer return"),
        (MovementType.DISPOSAL, MovementReason.EXPIRED, -4, "Expired stock removal"),
        (MovementType.RESERVATION, MovementReason.ONLINE_RESERVATION, -2, "Online reservation"),
    ]

    created = 0
    quantity = int(item.physical_stock)
    for idx, (movement_type, reason, delta, notes) in enumerate(movements):
        reference_id = f"seed-movement-{movement_type.value}"
        existing = await session.execute(
            select(StockMovement.id).where(StockMovement.reference_id == reference_id)
        )
        if existing.scalar_one_or_none():
            continue
        before = quantity
        after = max(0, before + delta)
        delta = after - before
        movement = StockMovement(
            inventory_item_id=item.id,
            movement_type=movement_type,
            reason=reason,
            quantity_delta=delta,
            quantity_before=before,
            quantity_after=after,
            user_id=user.id,
            reference_id=reference_id,
            reference_type="seed",
            notes=notes,
            created_at=now - timedelta(hours=4 * (len(movements) - idx)),
            updated_at=now - timedelta(hours=4 * (len(movements) - idx)),
        )
        session.add(movement)
        quantity = after
        created += 1

    item.physical_stock = quantity
    return created


def main() -> None:
    asyncio.run(seed_inventory())


if __name__ == "__main__":
    main()
