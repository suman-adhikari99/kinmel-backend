#!/usr/bin/env python3
"""
Seed orders with items, substitutions, status history, and contacts.

Usage:
  python scripts/seed_orders_data.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.core.security import Role, hash_password
from src.modules.orders.models import (
    ContactChannel,
    Order,
    OrderContactAttempt,
    OrderItem,
    OrderItemSubstitution,
    OrderStatus,
    OrderStatusHistory,
    OrderType,
    SubstitutionStatus,
)
from src.modules.products.models import Product, ProductStatus
from src.modules.users.models import User


ORDER_CUSTOMERS = [
    {"name": "Ava Patel", "phone": "+61 400 200 001", "email": "ava@example.com"},
    {"name": "Liam Chen", "phone": "+61 400 200 002", "email": "liam@example.com"},
    {"name": "Noah Brown", "phone": "+61 400 200 003", "email": "noah@example.com"},
    {"name": "Mia Singh", "phone": "+61 400 200 004", "email": "mia@example.com"},
    {"name": "Ethan Park", "phone": "+61 400 200 005", "email": "ethan@example.com"},
    {"name": "Zoe Taylor", "phone": "+61 400 200 006", "email": "zoe@example.com"},
]


async def ensure_user(session) -> User:
    user = (
        await session.execute(select(User).where(User.email == "orders-bot@kinmel-test.local"))
    ).scalar_one_or_none()
    if user:
        return user
    user = User(
        email="orders-bot@kinmel-test.local",
        password_hash=hash_password("TestPassword123!"),
        full_name="Orders Bot (Seed)",
        phone=None,
        avatar_url="https://images.unsplash.com/photo-1524504388940-b1c1722653e1?auto=format&fit=crop&w=600&q=60",
        role=Role.MANAGER,
        is_verified=True,
    )
    session.add(user)
    await session.flush()
    return user


async def ensure_products(session) -> list[Product]:
    products = (await session.execute(select(Product))).scalars().all()
    if products:
        return products
    fallback = [
        Product(
            sku="ORDER-SEED-APPLE",
            name="Seed Apple",
            description="Fallback apple for orders seed",
            category="Produce",
            brand="Seed Orchard",
            unit_price=Decimal("2.50"),
            cost_price=Decimal("1.20"),
            tax_rate=Decimal("0.10"),
            status=ProductStatus.ACTIVE,
            featured=False,
            priority=0,
            unit_of_measure="each",
            pack_size=1,
            is_perishable=True,
            shelf_life_days=10,
            requires_cold_storage=True,
            image_url="https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?auto=format&fit=crop&w=800&q=60",
        ),
        Product(
            sku="ORDER-SEED-BREAD",
            name="Seed Bread",
            description="Fallback bread for orders seed",
            category="Bakery",
            brand="Seed Bakery",
            unit_price=Decimal("4.80"),
            cost_price=Decimal("2.40"),
            tax_rate=Decimal("0.10"),
            status=ProductStatus.ACTIVE,
            featured=False,
            priority=0,
            unit_of_measure="each",
            pack_size=1,
            is_perishable=True,
            shelf_life_days=4,
            requires_cold_storage=False,
            image_url="https://images.unsplash.com/photo-1509440159596-0249088772ff?auto=format&fit=crop&w=800&q=60",
        ),
    ]
    session.add_all(fallback)
    await session.flush()
    return fallback


async def seed_orders() -> None:
    async with async_session_factory() as session:
        products = await ensure_products(session)
        user = await ensure_user(session)

        statuses = [
            OrderStatus.NEW,
            OrderStatus.PREPARING,
            OrderStatus.READY,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.COMPLETED,
            OrderStatus.CANCELLED,
        ]

        created = 0
        now = datetime.now(UTC)
        for idx, status in enumerate(statuses):
            order_id = str(uuid5(NAMESPACE_DNS, f"seed-order-{status.value}"))
            existing = await session.execute(select(Order).where(Order.id == order_id))
            if existing.scalar_one_or_none():
                continue

            order_type = OrderType.DELIVERY if idx % 2 else OrderType.PICKUP
            customer = ORDER_CUSTOMERS[idx % len(ORDER_CUSTOMERS)]
            created_at = now - timedelta(days=10 - idx, hours=idx)

            delivery_fee = Decimal("6.00") if order_type == OrderType.DELIVERY else Decimal("0.00")
            subtotal = Decimal("0.00")
            gst = Decimal("0.00")

            order = Order(
                id=order_id,
                order_type=order_type,
                status=status,
                time_slot="10:00-12:00" if order_type == OrderType.DELIVERY else "09:00-10:00",
                customer_name=customer["name"],
                customer_phone=customer["phone"],
                customer_email=customer["email"],
                delivery_address="123 Market St, Sydney NSW 2000" if order_type == OrderType.DELIVERY else None,
                delivery_suburb="Sydney" if order_type == OrderType.DELIVERY else None,
                subtotal=Decimal("0.00"),
                gst=Decimal("0.00"),
                delivery_fee=delivery_fee,
                total=Decimal("0.00"),
                notes="Seeded order for reporting and UI",
                has_substitutions=False,
                created_at=created_at,
                updated_at=created_at,
                delivered_at=created_at if status == OrderStatus.COMPLETED else None,
            )
            session.add(order)

            for j in range(2):
                product = products[(idx + j) % len(products)]
                qty = Decimal(1 + j)
                item = OrderItem(
                    id=str(uuid5(NAMESPACE_DNS, f"{order_id}-item-{j + 1}")),
                    order_id=order.id,
                    product_sku=product.sku,
                    name=product.name,
                    quantity=qty,
                    price=product.unit_price,
                    checked=status in {
                        OrderStatus.READY,
                        OrderStatus.OUT_FOR_DELIVERY,
                        OrderStatus.COMPLETED,
                    },
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(item)
                subtotal += product.unit_price * qty

                if idx == 1 and j == 0:
                    order.has_substitutions = True
                    substitution = OrderItemSubstitution(
                        order_item_id=item.id,
                        original_item_id="ORIG-ITEM-001",
                        original_name=f"{product.name} (Original)",
                        original_price=product.unit_price,
                        original_qty=qty,
                        reason="Out of stock",
                        price_difference=Decimal("1.00"),
                        customer_notified=True,
                        status=SubstitutionStatus.APPROVED,
                        substitute_item_id="SUB-ITEM-001",
                        substitute_name="Substitute Item",
                        substitute_price=product.unit_price + Decimal("1.00"),
                        quantity=qty,
                    )
                    session.add(substitution)

            gst = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
            total = subtotal + gst + delivery_fee
            order.subtotal = subtotal
            order.gst = gst
            order.total = total

            history_statuses = [OrderStatus.NEW, status]
            if status in {OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.COMPLETED}:
                history_statuses.insert(1, OrderStatus.PREPARING)
            for h_idx, hist_status in enumerate(history_statuses):
                history = OrderStatusHistory(
                    order_id=order.id,
                    status=hist_status,
                    changed_by=user.id,
                    created_at=created_at + timedelta(hours=h_idx),
                    updated_at=created_at + timedelta(hours=h_idx),
                )
                session.add(history)

            if idx == 2:
                for channel in [
                    ContactChannel.CALL,
                    ContactChannel.SMS,
                    ContactChannel.EMAIL,
                    ContactChannel.WHATSAPP,
                ]:
                    contact = OrderContactAttempt(
                        order_id=order.id,
                        channel=channel,
                        template_id=f"seed-{channel.value}",
                        notes=f"Seed contact via {channel.value}",
                        created_at=created_at + timedelta(hours=4),
                        updated_at=created_at + timedelta(hours=4),
                    )
                    session.add(contact)

            created += 1

        await session.commit()
        print(f"Seeded orders: {created}")


def main() -> None:
    asyncio.run(seed_orders())


if __name__ == "__main__":
    main()
