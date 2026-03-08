#!/usr/bin/env python3
"""
Seed comprehensive dashboard test data in one command.

This script orchestrates all dashboard-relevant seeders and prints a
coverage summary so you can quickly verify data variety.

It also applies a final coverage pass to ensure every dashboard-facing
enum/type bucket has at least one record.

Usage:
  python scripts/seed_dashboard_data.py
  python scripts/seed_dashboard_data.py --clear --force
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import and_, case, func, select

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory, close_db
from src.core.security import Role, hash_password
from src.modules.customers.repository import _CUSTOMERS
from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.notifications.models import (
    Notification,
    NotificationRead,
    NotificationType,
)
from src.modules.orders.models import (
    ContactChannel,
    Order,
    OrderContactAttempt,
    OrderExportJob,
    OrderExportStatus,
    OrderItem,
    OrderItemSubstitution,
    OrderStatus,
    OrderType,
    SubstitutionStatus,
)
from src.modules.pos.models import PosSale, PosSaleLine, PosSaleStatus
from src.modules.products.models import (
    Category,
    CategoryStatus,
    Product,
    ProductBarcode,
    ProductStatus,
)
from src.modules.reports.models import (
    ReportExport,
    ReportExportStatus,
    ReportFormat,
)
from src.modules.revenue.models import (
    AdjustmentType,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    RevenueAdjustment,
    RevenuePayment,
    RevenuePayout,
)
from src.modules.users.models import User


SEED_STEPS = [
    ("core", ["scripts/seed_data.py", "--all"]),
    ("categories", ["scripts/seed_categories_data.py"]),
    ("users", ["scripts/seed_users_data.py"]),
    ("products", ["scripts/seed_products_data.py"]),
    ("inventory", ["scripts/seed_inventory_data.py"]),
    ("orders", ["scripts/seed_orders_data.py"]),
    ("revenue", ["scripts/seed_revenue_data.py"]),
    ("reports", ["scripts/seed_reports_data.py"]),
    ("notifications", ["scripts/seed_notifications_data.py"]),
]

REPORT_DIR = Path(PROJECT_ROOT) / "uploads" / "reports"
TEST_PASSWORD = "TestPassword123!"
TARGET_MIN_PER_TYPE = 6
REPORT_IDS = ("sales", "orders", "xero")
UTC = timezone.utc


def run_step(step_name: str, command: list[str]) -> None:
    full_command = [sys.executable, *command]
    print(f"-> Running {step_name}: {' '.join(full_command)}")
    result = subprocess.run(full_command, cwd=PROJECT_ROOT, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"Step failed: {step_name}")


def _value(raw) -> str:
    return raw.value if hasattr(raw, "value") else str(raw)


def _seed_id(seed: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"seed-dashboard-coverage:{seed}"))


def _enum_values(enum_cls) -> list[str]:
    return [member.value for member in enum_cls]


def _ordered_counts(counts: dict[str, int], expected: list[str]) -> dict[str, int]:
    ordered: dict[str, int] = {}
    for key in expected:
        ordered[key] = int(counts.get(key, 0))
    for key, value in counts.items():
        if key not in ordered:
            ordered[key] = int(value)
    return ordered


def _missing_keys(counts: dict[str, int]) -> list[str]:
    return [key for key, value in counts.items() if int(value) == 0]


def _below_target_keys(counts: dict[str, int], target: int) -> list[str]:
    return [key for key, value in counts.items() if int(value) < target]


async def _ensure_reference_user(session) -> User:
    preferred_emails = [
        "owner@kinmel-test.local",
        "manager@kinmel-test.local",
        "supervisor@kinmel-test.local",
    ]
    for email in preferred_emails:
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            return existing

    any_user = (await session.execute(select(User).limit(1))).scalar_one_or_none()
    if any_user:
        return any_user

    user = User(
        id=_seed_id("coverage-user"),
        email="coverage-bot@kinmel-test.local",
        password_hash=hash_password(TEST_PASSWORD),
        full_name="Dashboard Coverage Bot",
        role=Role.MANAGER,
        is_verified=True,
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _ensure_reference_order(session) -> Order:
    order = (
        await session.execute(
            select(Order).order_by(Order.created_at.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if order:
        return order

    now = datetime.now(UTC)
    order_id = _seed_id("coverage-order-fallback")
    existing = (
        await session.execute(select(Order).where(Order.id == order_id))
    ).scalar_one_or_none()
    if existing:
        return existing

    order = Order(
        id=order_id,
        order_type=OrderType.PICKUP,
        status=OrderStatus.NEW,
        time_slot="10:00-12:00",
        customer_name="Coverage Fallback",
        customer_phone="+61 400 555 999",
        customer_email="coverage-fallback@example.com",
        delivery_address=None,
        delivery_suburb=None,
        subtotal=Decimal("20.00"),
        gst=Decimal("2.00"),
        delivery_fee=Decimal("0.00"),
        total=Decimal("22.00"),
        notes="Fallback order for coverage seeding",
        has_substitutions=False,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(days=1),
    )
    session.add(order)
    await session.flush()

    item = OrderItem(
        id=_seed_id("coverage-order-fallback-item"),
        order_id=order.id,
        product_sku=None,
        name="Coverage Item",
        quantity=Decimal("1.00"),
        price=Decimal("20.00"),
        checked=False,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )
    session.add(item)
    await session.flush()
    return order


async def _ensure_user_minimums(session, target: int) -> User:
    users = (await session.execute(select(User))).scalars().all()
    status_counts = {"active": 0, "invited": 0, "inactive": 0, "canceled": 0}
    role_counts: dict[str, int] = {role.value: 0 for role in Role}
    for user in users:
        role_key = _value(user.role)
        role_counts[role_key] = role_counts.get(role_key, 0) + 1
        if user.is_active and user.is_verified:
            status_counts["active"] += 1
        elif user.is_active and not user.is_verified:
            status_counts["invited"] += 1
        elif (not user.is_active) and user.is_verified:
            status_counts["inactive"] += 1
        else:
            status_counts["canceled"] += 1

    now = datetime.now(UTC)
    status_templates = {
        "active": {"is_active": True, "is_verified": True},
        "invited": {
            "is_active": True,
            "is_verified": False,
            "invited_at": now - timedelta(days=1),
            "invite_expires_at": now + timedelta(days=3),
        },
        "inactive": {"is_active": False, "is_verified": True},
        "canceled": {
            "is_active": False,
            "is_verified": False,
            "invited_at": now - timedelta(days=8),
            "invite_expires_at": now - timedelta(days=1),
            "deleted_at": now - timedelta(days=1),
        },
    }

    for status_key, template in status_templates.items():
        for rank in range(status_counts.get(status_key, 0) + 1, target + 1):
            user_id = _seed_id(f"coverage-user-status-{status_key}-{rank}")
            existing = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if existing:
                continue
            invite_token = None
            if status_key in {"invited", "canceled"}:
                invite_token = f"seed-{status_key}-{rank}"
            user = User(
                id=user_id,
                email=f"seed-{status_key}-{rank}@kinmel-test.local",
                password_hash=hash_password(TEST_PASSWORD),
                full_name=f"Seed {status_key.title()} User {rank}",
                role=Role.STAFF,
                is_active=template.get("is_active", True),
                is_verified=template.get("is_verified", True),
                invited_at=template.get("invited_at"),
                invite_expires_at=template.get("invite_expires_at"),
                invite_token=invite_token,
                deleted_at=template.get("deleted_at"),
            )
            session.add(user)

    for role in Role:
        role_key = role.value
        current = role_counts.get(role_key, 0)
        for rank in range(current + 1, target + 1):
            user_id = _seed_id(f"coverage-user-role-{role_key}-{rank}")
            existing = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if existing:
                continue
            user = User(
                id=user_id,
                email=f"seed-role-{role_key}-{rank}@kinmel-test.local",
                password_hash=hash_password(TEST_PASSWORD),
                full_name=f"Seed {role_key.title()} Role {rank}",
                role=role,
                is_active=True,
                is_verified=True,
            )
            session.add(user)

    await session.flush()
    return await _ensure_reference_user(session)


async def _ensure_category_status_minimums(session, target: int) -> None:
    rows = await session.execute(
        select(Category.status, func.count(Category.id)).group_by(Category.status)
    )
    counts = {_value(status): int(count) for status, count in rows.all()}
    now = datetime.now(UTC)

    for status in CategoryStatus:
        current = counts.get(status.value, 0)
        for rank in range(current + 1, target + 1):
            category_id = _seed_id(f"coverage-category-{status.value}-{rank}")
            existing = (
                await session.execute(select(Category).where(Category.id == category_id))
            ).scalar_one_or_none()
            if existing:
                continue
            session.add(
                Category(
                    id=category_id,
                    name=f"Coverage {status.value.title()} Category {rank}",
                    description=f"Coverage category for status={status.value}",
                    status=status,
                    featured=False,
                    priority=max(0, 100 - rank),
                    image_url=None,
                    image_file=None,
                    is_active=True,
                    created_at=now - timedelta(days=rank),
                    updated_at=now - timedelta(days=rank),
                )
            )

    await session.flush()


async def _ensure_product_status_minimums(session, target: int) -> None:
    rows = await session.execute(
        select(Product.status, func.count(Product.id)).group_by(Product.status)
    )
    counts = {_value(status): int(count) for status, count in rows.all()}

    category = (
        await session.execute(
            select(Category).where(Category.is_active == True).order_by(Category.name).limit(1)
        )
    ).scalar_one_or_none()
    category_name = category.name if category else "other"
    now = datetime.now(UTC)

    for status in ProductStatus:
        current = counts.get(status.value, 0)
        for rank in range(current + 1, target + 1):
            product_id = _seed_id(f"coverage-product-{status.value}-{rank}")
            existing = (
                await session.execute(select(Product).where(Product.id == product_id))
            ).scalar_one_or_none()
            if existing:
                continue
            sku = f"COV-{status.value[:3].upper()}-{rank:03d}-{product_id[:4].upper()}"
            session.add(
                Product(
                    id=product_id,
                    sku=sku,
                    name=f"Coverage {status.value.title()} Product {rank}",
                    description=f"Coverage product for status={status.value}",
                    category=category_name,
                    brand="Coverage",
                    subcategory="Coverage",
                    image_url=None,
                    image_file=None,
                    unit_price=Decimal("9.99"),
                    cost_price=Decimal("5.00"),
                    tax_rate=Decimal("0.10"),
                    status=status,
                    featured=False,
                    priority=0,
                    unit_of_measure="each",
                    pack_size=1,
                    is_perishable=False,
                    shelf_life_days=None,
                    requires_cold_storage=False,
                    barcode=f"COVBAR{abs(hash(sku)) % 10_000_000_000:010d}",
                    is_active=True,
                    created_at=now - timedelta(days=rank),
                    updated_at=now - timedelta(days=rank),
                )
            )

    await session.flush()


async def _ensure_inventory_state_minimums(session, target: int) -> None:
    location = (
        await session.execute(
            select(Location).where(Location.is_active == True).order_by(Location.code).limit(1)
        )
    ).scalar_one_or_none()
    if not location:
        return

    counts_row = await session.execute(
        select(
            func.sum(case((InventoryItem.physical_stock == 0, 1), else_=0)),
            func.sum(
                case(
                    (
                        and_(
                            InventoryItem.physical_stock > 0,
                            InventoryItem.physical_stock <= InventoryItem.reorder_point,
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
            func.sum(case((InventoryItem.physical_stock > InventoryItem.reorder_point, 1), else_=0)),
        )
        .select_from(InventoryItem)
        .where(InventoryItem.is_active == True)
    )
    out_count, low_count, in_count = counts_row.one()
    state_counts = {
        "out_of_stock": int(out_count or 0),
        "low_stock": int(low_count or 0),
        "in_stock": int(in_count or 0),
    }

    product_category = (
        await session.execute(
            select(Category).where(Category.is_active == True).order_by(Category.name).limit(1)
        )
    ).scalar_one_or_none()
    category_name = product_category.name if product_category else "other"

    specs = {
        "out_of_stock": {"physical_stock": 0, "reorder_point": 5},
        "low_stock": {"physical_stock": 2, "reorder_point": 5},
        "in_stock": {"physical_stock": 12, "reorder_point": 5},
    }
    now = datetime.now(UTC)

    for state_key, config in specs.items():
        for rank in range(state_counts.get(state_key, 0) + 1, target + 1):
            product_id = _seed_id(f"coverage-inventory-product-{state_key}-{rank}")
            existing_product = (
                await session.execute(select(Product).where(Product.id == product_id))
            ).scalar_one_or_none()
            if not existing_product:
                sku = f"COV-INV-{state_key[:3].upper()}-{rank:03d}"
                product = Product(
                    id=product_id,
                    sku=sku,
                    name=f"Coverage Inventory {state_key.replace('_', ' ').title()} {rank}",
                    description=f"Coverage inventory product for {state_key}",
                    category=category_name,
                    brand="Coverage",
                    subcategory="Inventory",
                    unit_price=Decimal("4.50"),
                    cost_price=Decimal("2.40"),
                    tax_rate=Decimal("0.10"),
                    status=ProductStatus.ACTIVE,
                    featured=False,
                    priority=0,
                    unit_of_measure="each",
                    pack_size=1,
                    is_perishable=False,
                    shelf_life_days=None,
                    requires_cold_storage=False,
                    barcode=f"COVINV{abs(hash(sku)) % 10_000_000_000:010d}",
                    is_active=True,
                    created_at=now - timedelta(hours=rank),
                    updated_at=now - timedelta(hours=rank),
                )
                session.add(product)
                await session.flush()
            else:
                product = existing_product

            item_id = _seed_id(f"coverage-inventory-item-{state_key}-{rank}")
            existing_item = (
                await session.execute(select(InventoryItem).where(InventoryItem.id == item_id))
            ).scalar_one_or_none()
            if existing_item:
                continue
            session.add(
                InventoryItem(
                    id=item_id,
                    product_id=product.id,
                    location_id=location.id,
                    physical_stock=config["physical_stock"],
                    buffer=0,
                    reorder_point=config["reorder_point"],
                    max_stock=20,
                    is_active=True,
                    created_at=now - timedelta(hours=rank),
                    updated_at=now - timedelta(hours=rank),
                )
            )

    await session.flush()


async def _ensure_order_status_type_minimums(session, target: int) -> None:
    status_rows = await session.execute(
        select(Order.status, func.count(Order.id)).group_by(Order.status)
    )
    status_counts = {_value(status): int(count) for status, count in status_rows.all()}

    type_rows = await session.execute(
        select(Order.order_type, func.count(Order.id)).group_by(Order.order_type)
    )
    type_counts = {_value(order_type): int(count) for order_type, count in type_rows.all()}

    product = (
        await session.execute(
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not product:
        return

    now = datetime.now(UTC)

    async def _create_order(status: OrderStatus, order_type: OrderType, rank: int, tag: str) -> None:
        order_id = _seed_id(f"coverage-order-{tag}-{status.value}-{order_type.value}-{rank}")
        existing = (
            await session.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if existing:
            return
        created_at = now - timedelta(hours=rank)
        delivery_fee = Decimal("6.00") if order_type == OrderType.DELIVERY else Decimal("0.00")
        subtotal = Decimal("20.00")
        gst = Decimal("2.00")
        total = subtotal + gst + delivery_fee
        order = Order(
            id=order_id,
            order_type=order_type,
            status=status,
            time_slot="10:00-12:00" if order_type == OrderType.DELIVERY else "09:00-10:00",
            customer_name=f"Coverage {status.value.title()} {rank}",
            customer_phone=f"+61 411 {rank:03d} {rank:03d}",
            customer_email=f"coverage-order-{status.value}-{order_type.value}-{rank}@example.com",
            delivery_address="1 Coverage St, Sydney NSW 2000" if order_type == OrderType.DELIVERY else None,
            delivery_suburb="Sydney" if order_type == OrderType.DELIVERY else None,
            subtotal=subtotal,
            gst=gst,
            delivery_fee=delivery_fee,
            total=total,
            notes="Coverage seeded order",
            has_substitutions=False,
            delivered_at=created_at + timedelta(hours=2) if status == OrderStatus.COMPLETED else None,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(order)
        session.add(
            OrderItem(
                id=_seed_id(f"coverage-order-item-{tag}-{status.value}-{order_type.value}-{rank}"),
                order_id=order.id,
                product_sku=product.sku,
                name=product.name,
                quantity=Decimal("1.00"),
                price=product.unit_price,
                checked=status in {OrderStatus.READY, OrderStatus.OUT_FOR_DELIVERY, OrderStatus.COMPLETED},
                created_at=created_at,
                updated_at=created_at,
            )
        )

    for status in OrderStatus:
        current = status_counts.get(status.value, 0)
        for rank in range(current + 1, target + 1):
            order_type = OrderType.DELIVERY if rank % 2 == 0 else OrderType.PICKUP
            await _create_order(status, order_type, rank, "status")

    await session.flush()

    type_rows = await session.execute(
        select(Order.order_type, func.count(Order.id)).group_by(Order.order_type)
    )
    type_counts = {_value(order_type): int(count) for order_type, count in type_rows.all()}
    for order_type in OrderType:
        current = type_counts.get(order_type.value, 0)
        for rank in range(current + 1, target + 1):
            await _create_order(OrderStatus.COMPLETED, order_type, rank, "type")

    await session.flush()


async def _ensure_location_type_coverage(session, target: int) -> None:
    rows = await session.execute(
        select(Location.location_type, func.count(Location.id))
        .where(Location.is_active == True)
        .group_by(Location.location_type)
    )
    counts = {_value(location_type): int(count) for location_type, count in rows.all()}

    metadata = {
        LocationType.FLOOR: ("SEED-FLOOR", "Seed Floor Zone", None),
        LocationType.COLD_STORAGE: ("SEED-COLD", "Seed Cold Storage", "chilled"),
        LocationType.BACKROOM: ("SEED-BACK", "Seed Backroom", None),
        LocationType.RECEIVING: ("SEED-RECV", "Seed Receiving Dock", None),
        LocationType.DAMAGED: ("SEED-DMG", "Seed Damaged Goods Bay", None),
    }

    for location_type in LocationType:
        prefix, base_name, temp_zone = metadata[location_type]
        current = counts.get(location_type.value, 0)
        for rank in range(current + 1, target + 1):
            code = f"{prefix}-{rank:02d}"
            existing_code = (
                await session.execute(select(Location).where(Location.code == code))
            ).scalar_one_or_none()
            if existing_code:
                continue
            session.add(
                Location(
                    id=_seed_id(f"coverage-location-{location_type.value}-{rank}"),
                    code=code,
                    name=f"{base_name} {rank}",
                    location_type=location_type,
                    capacity=300,
                    temperature_zone=temp_zone,
                    notes="Coverage seed location",
                    is_active=True,
                )
            )
    await session.flush()


async def _ensure_product_barcode_coverage(session, target: int) -> Product | None:
    product = (
        await session.execute(
            select(Product)
            .where(Product.is_active == True)
            .order_by(Product.updated_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not product:
        return None

    if not product.barcode:
        product.barcode = f"COV{uuid5(NAMESPACE_DNS, product.sku).hex[:11]}".upper()

    primary = (
        await session.execute(
            select(ProductBarcode).where(
                ProductBarcode.product_id == product.id,
                ProductBarcode.is_primary == True,
            )
        )
    ).scalar_one_or_none()
    if not primary:
        existing_primary_barcode = (
            await session.execute(
                select(ProductBarcode).where(ProductBarcode.barcode == product.barcode)
            )
        ).scalar_one_or_none()
        if not existing_primary_barcode:
            session.add(
                ProductBarcode(
                    id=_seed_id("coverage-product-primary-barcode"),
                    product_id=product.id,
                    barcode=product.barcode,
                    is_primary=True,
                )
            )

    barcode_total = int(
        (await session.execute(select(func.count(ProductBarcode.id)))).scalar_one() or 0
    )
    for rank in range(barcode_total + 1, target + 1):
        barcode = f"COV-ALIAS-{rank:03d}-{uuid5(NAMESPACE_DNS, f'{product.sku}-{rank}').hex[:8].upper()}"
        existing = (
            await session.execute(
                select(ProductBarcode).where(ProductBarcode.barcode == barcode)
            )
        ).scalar_one_or_none()
        if existing:
            continue
        session.add(
            ProductBarcode(
                id=_seed_id(f"coverage-barcode-alias-{rank}"),
                product_id=product.id,
                barcode=barcode,
                is_primary=False,
            )
        )

    await session.flush()
    return product


async def _ensure_movement_reason_coverage(session, user: User, target: int) -> None:
    item = (
        await session.execute(
            select(InventoryItem)
            .where(InventoryItem.is_active == True)
            .order_by(InventoryItem.physical_stock.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not item:
        return

    reason_specs = {
        MovementReason.SUPPLIER_DELIVERY: (MovementType.RECEIVING, 4, "Coverage supplier delivery"),
        MovementReason.INTERNAL_TRANSFER: (MovementType.TRANSFER, -1, "Coverage internal transfer"),
        MovementReason.CUSTOMER_SALE: (MovementType.SALE, -1, "Coverage sale"),
        MovementReason.EXPIRED: (MovementType.DISPOSAL, -1, "Coverage expiry disposal"),
        MovementReason.DAMAGED: (MovementType.DISPOSAL, -1, "Coverage damaged disposal"),
        MovementReason.THEFT: (MovementType.ADJUSTMENT, -1, "Coverage theft adjustment"),
        MovementReason.SHRINKAGE: (MovementType.ADJUSTMENT, -1, "Coverage shrinkage adjustment"),
        MovementReason.CYCLE_COUNT: (MovementType.ADJUSTMENT, 1, "Coverage cycle count"),
        MovementReason.AUDIT_CORRECTION: (MovementType.ADJUSTMENT, 1, "Coverage audit correction"),
        MovementReason.SYSTEM_CORRECTION: (MovementType.ADJUSTMENT, 1, "Coverage system correction"),
        MovementReason.CUSTOMER_RETURN: (MovementType.RETURN, 1, "Coverage customer return"),
        MovementReason.ONLINE_RESERVATION: (MovementType.RESERVATION, -1, "Coverage online reservation"),
        MovementReason.RESERVATION_RELEASED: (MovementType.RESERVATION, 1, "Coverage reservation release"),
    }

    reason_rows = await session.execute(
        select(StockMovement.reason, func.count(StockMovement.id)).group_by(StockMovement.reason)
    )
    reason_counts = {_value(reason): int(count) for reason, count in reason_rows.all()}

    current_qty = int(item.physical_stock or 0)
    now = datetime.now(UTC)
    movement_idx = 0

    for reason in MovementReason:
        movement_type, delta, note = reason_specs[reason]
        current = reason_counts.get(reason.value, 0)
        for rank in range(current + 1, target + 1):
            reference_id = f"seed-dashboard-reason-{reason.value}-{rank}"
            existing = (
                await session.execute(
                    select(StockMovement.id).where(StockMovement.reference_id == reference_id)
                )
            ).scalar_one_or_none()
            if existing:
                continue

            qty_before = current_qty
            qty_after = max(0, qty_before + delta)
            effective_delta = qty_after - qty_before
            timestamp = now - timedelta(minutes=movement_idx + 1)

            session.add(
                StockMovement(
                    id=_seed_id(f"coverage-movement-{reason.value}-{rank}"),
                    inventory_item_id=item.id,
                    movement_type=movement_type,
                    reason=reason,
                    quantity_delta=effective_delta,
                    quantity_before=qty_before,
                    quantity_after=qty_after,
                    user_id=user.id,
                    reference_id=reference_id,
                    reference_type="seed",
                    notes=note,
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )
            current_qty = qty_after
            movement_idx += 1

    item.physical_stock = current_qty
    await session.flush()


async def _ensure_substitution_status_coverage(session, target: int) -> None:
    status_rows = await session.execute(
        select(OrderItemSubstitution.status, func.count(OrderItemSubstitution.id)).group_by(
            OrderItemSubstitution.status
        )
    )
    existing_statuses = {_value(status): int(count) for status, count in status_rows.all()}
    missing_counts = {
        status: max(0, target - int(existing_statuses.get(status.value, 0)))
        for status in SubstitutionStatus
    }
    needed = sum(missing_counts.values())
    if needed <= 0:
        return

    available_items = (
        await session.execute(
            select(OrderItem)
            .outerjoin(
                OrderItemSubstitution,
                OrderItemSubstitution.order_item_id == OrderItem.id,
            )
            .where(OrderItemSubstitution.id.is_(None))
            .order_by(OrderItem.created_at.desc())
        )
    ).scalars().all()

    while len(available_items) < needed:
        order = await _ensure_reference_order(session)
        created_at = datetime.now(UTC)
        extra_item = OrderItem(
            id=_seed_id(f"coverage-extra-order-item-{len(available_items) + 1}"),
            order_id=order.id,
            product_sku=None,
            name=f"Coverage Substitution Item {len(available_items) + 1}",
            quantity=Decimal("1.00"),
            price=Decimal("9.99"),
            checked=False,
            created_at=created_at,
            updated_at=created_at,
        )
        session.add(extra_item)
        await session.flush()
        available_items.append(extra_item)

    item_index = 0
    for status in SubstitutionStatus:
        for rank in range(
            int(existing_statuses.get(status.value, 0)) + 1,
            target + 1,
        ):
            item = available_items[item_index]
            item_index += 1
            substitution_id = _seed_id(f"coverage-substitution-{status.value}-{rank}")
            existing_substitution = (
                await session.execute(
                    select(OrderItemSubstitution).where(OrderItemSubstitution.id == substitution_id)
                )
            ).scalar_one_or_none()
            if existing_substitution:
                continue
            session.add(
                OrderItemSubstitution(
                    id=substitution_id,
                    order_item_id=item.id,
                    original_item_id=item.product_sku,
                    original_name=item.name,
                    original_price=item.price,
                    original_qty=item.quantity,
                    reason=f"Coverage substitution ({status.value})",
                    price_difference=Decimal("0.00"),
                    customer_notified=False,
                    status=status,
                    substitute_item_id=item.product_sku,
                    substitute_name=f"{item.name} Substitute",
                    substitute_price=item.price,
                    quantity=item.quantity,
                )
            )
            order = (
                await session.execute(select(Order).where(Order.id == item.order_id))
            ).scalar_one_or_none()
            if order:
                order.has_substitutions = True

    await session.flush()


async def _ensure_contact_channel_coverage(session, target: int) -> None:
    order = await _ensure_reference_order(session)
    rows = await session.execute(
        select(OrderContactAttempt.channel, func.count(OrderContactAttempt.id)).group_by(
            OrderContactAttempt.channel
        )
    )
    existing_channels = {_value(channel): int(count) for channel, count in rows.all()}
    now = datetime.now(UTC)

    for idx, channel in enumerate(ContactChannel):
        current = existing_channels.get(channel.value, 0)
        for rank in range(current + 1, target + 1):
            timestamp = now - timedelta(minutes=(idx * target) + rank + 30)
            attempt_id = _seed_id(f"coverage-contact-{channel.value}-{rank}")
            existing_attempt = (
                await session.execute(
                    select(OrderContactAttempt).where(OrderContactAttempt.id == attempt_id)
                )
            ).scalar_one_or_none()
            if existing_attempt:
                continue
            session.add(
                OrderContactAttempt(
                    id=attempt_id,
                    order_id=order.id,
                    channel=channel,
                    template_id=f"coverage-{channel.value}-{rank}",
                    notes=f"Coverage contact via {channel.value}",
                    created_at=timestamp,
                    updated_at=timestamp,
                )
            )

    await session.flush()


async def _ensure_revenue_coverage(session, target: int) -> None:
    order = await _ensure_reference_order(session)
    rows_by_method = await session.execute(
        select(RevenuePayment.method, func.count(RevenuePayment.id)).group_by(RevenuePayment.method)
    )
    existing_methods = {_value(method) for method, _ in rows_by_method.all()}

    rows_by_status = await session.execute(
        select(RevenuePayment.status, func.count(RevenuePayment.id)).group_by(RevenuePayment.status)
    )
    existing_statuses = {_value(status) for status, _ in rows_by_status.all()}

    now = datetime.now(UTC)
    method_counts = {_value(method): int(count) for method, count in rows_by_method.all()}
    status_counts = {_value(status): int(count) for status, count in rows_by_status.all()}

    for idx, method in enumerate(PaymentMethod):
        current = method_counts.get(method.value, 0)
        for rank in range(current + 1, target + 1):
            payment_id = _seed_id(f"coverage-payment-method-{method.value}-{rank}")
            existing_payment = (
                await session.execute(select(RevenuePayment).where(RevenuePayment.id == payment_id))
            ).scalar_one_or_none()
            if existing_payment:
                continue
            session.add(
                RevenuePayment(
                    id=payment_id,
                    order_id=order.id,
                    method=method,
                    status=PaymentStatus.COMPLETED,
                    amount=(Decimal("25.00") + Decimal(idx) + Decimal(rank) / Decimal("10")).quantize(
                        Decimal("0.01")
                    ),
                    created_at=now - timedelta(hours=idx + rank),
                    updated_at=now - timedelta(hours=idx + rank),
                )
            )

    for idx, payment_status in enumerate(PaymentStatus):
        current = status_counts.get(payment_status.value, 0)
        for rank in range(current + 1, target + 1):
            payment_id = _seed_id(f"coverage-payment-status-{payment_status.value}-{rank}")
            existing_payment = (
                await session.execute(select(RevenuePayment).where(RevenuePayment.id == payment_id))
            ).scalar_one_or_none()
            if existing_payment:
                continue
            session.add(
                RevenuePayment(
                    id=payment_id,
                    order_id=order.id,
                    method=PaymentMethod.CREDIT_CARD,
                    status=payment_status,
                    amount=(Decimal("30.00") + Decimal(idx) + Decimal(rank) / Decimal("10")).quantize(
                        Decimal("0.01")
                    ),
                    created_at=now - timedelta(hours=idx + rank + 10),
                    updated_at=now - timedelta(hours=idx + rank + 10),
                )
            )

    payout_rows = await session.execute(
        select(RevenuePayout.status, func.count(RevenuePayout.id)).group_by(RevenuePayout.status)
    )
    existing_payout_statuses = {_value(status): int(count) for status, count in payout_rows.all()}
    for idx, payout_status in enumerate(PayoutStatus):
        current = existing_payout_statuses.get(payout_status.value, 0)
        for rank in range(current + 1, target + 1):
            payout_id = _seed_id(f"coverage-payout-{payout_status.value}-{rank}")
            existing_payout = (
                await session.execute(select(RevenuePayout).where(RevenuePayout.id == payout_id))
            ).scalar_one_or_none()
            if existing_payout:
                continue
            payout_at = (now + timedelta(days=(idx * target) + rank)).strftime("%Y-%m-%dT%H:%M:%SZ")
            session.add(
                RevenuePayout(
                    id=payout_id,
                    payout_at=payout_at,
                    status=payout_status,
                    amount=(Decimal("400.00") + Decimal(idx * 50) + Decimal(rank)).quantize(
                        Decimal("0.01")
                    ),
                )
            )

    adjustment_rows = await session.execute(
        select(RevenueAdjustment.adjustment_type, func.count(RevenueAdjustment.id)).group_by(
            RevenueAdjustment.adjustment_type
        )
    )
    existing_adjustments = {_value(adj_type): int(count) for adj_type, count in adjustment_rows.all()}
    for idx, adj_type in enumerate(AdjustmentType):
        current = existing_adjustments.get(adj_type.value, 0)
        for rank in range(current + 1, target + 1):
            adjustment_id = _seed_id(f"coverage-adjustment-{adj_type.value}-{rank}")
            existing_adjustment = (
                await session.execute(
                    select(RevenueAdjustment).where(RevenueAdjustment.id == adjustment_id)
                )
            ).scalar_one_or_none()
            if existing_adjustment:
                continue
            session.add(
                RevenueAdjustment(
                    id=adjustment_id,
                    adjustment_type=adj_type,
                    amount=(Decimal("10.00") + Decimal(idx * 5) + Decimal(rank)).quantize(
                        Decimal("0.01")
                    ),
                    notes=f"Coverage adjustment ({adj_type.value})",
                )
            )

    await session.flush()


def _render_report_content(report_id: str, export_format: str) -> str:
    rows = [
        {"date": "2026-03-01", "total_sales": 120.0, "gst": 12.0, "orders": 4},
        {"date": "2026-03-02", "total_sales": 143.5, "gst": 14.35, "orders": 5},
    ]
    csv_header = ",".join(rows[0].keys())
    csv_rows = "\n".join(",".join(str(row[key]) for key in rows[0].keys()) for row in rows)
    content = f"{csv_header}\n{csv_rows}"
    if export_format == ReportFormat.PDF.value:
        return f"{report_id.title()} Report\n\n{content}\n"
    return content


async def _ensure_reports_coverage(session, target: int) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    # Create full report_id x format x status matrix.
    # With 3x3x3 = 27 exports, each dimension is guaranteed >= 6.
    combinations: list[tuple[str, str, str]] = []
    for report_id in REPORT_IDS:
        for export_format in ReportFormat:
            for export_status in ReportExportStatus:
                combinations.append((report_id, export_format.value, export_status.value))

    for idx, (report_id, export_format, export_status) in enumerate(combinations):
        export_id = _seed_id(f"coverage-report-{report_id}-{export_format}-{export_status}-1")
        existing = (
            await session.execute(select(ReportExport).where(ReportExport.id == export_id))
        ).scalar_one_or_none()
        if existing:
            continue

        created_at = now - timedelta(hours=idx + 1)
        file_path = None
        size_kb = None
        error_message = None

        if export_status == ReportExportStatus.READY.value:
            filename = (
                f"seed_dashboard_{report_id}_{export_format.lower()}_{created_at.strftime('%Y%m%d')}"
                f".{export_format.lower()}"
            )
            target_file = REPORT_DIR / filename
            target_file.write_text(_render_report_content(report_id, export_format), encoding="utf-8")
            file_path = str(target_file)
            size_kb = max(1, int(target_file.stat().st_size / 1024))
        elif export_status == ReportExportStatus.FAILED.value:
            error_message = "Coverage seeded failed export"

        session.add(
            ReportExport(
                id=export_id,
                report_id=report_id,
                format=export_format,
                status=export_status,
                file_path=file_path,
                size_kb=size_kb,
                error_message=error_message,
                created_at=created_at,
                updated_at=created_at,
            )
        )

    status_rows = await session.execute(
        select(ReportExport.status, func.count(ReportExport.id)).group_by(ReportExport.status)
    )
    status_counts = {_value(status): int(count) for status, count in status_rows.all()}

    format_rows = await session.execute(
        select(ReportExport.format, func.count(ReportExport.id)).group_by(ReportExport.format)
    )
    format_counts = {_value(report_format): int(count) for report_format, count in format_rows.all()}

    report_rows = await session.execute(
        select(ReportExport.report_id, func.count(ReportExport.id)).group_by(ReportExport.report_id)
    )
    report_counts = {_value(report_id): int(count) for report_id, count in report_rows.all()}

    # Backfill if existing datasets are highly skewed.
    for status in ReportExportStatus:
        current = status_counts.get(status.value, 0)
        for rank in range(current + 1, target + 1):
            report_id = REPORT_IDS[rank % len(REPORT_IDS)]
            export_format = list(ReportFormat)[rank % len(ReportFormat)].value
            export_id = _seed_id(f"coverage-report-backfill-status-{status.value}-{rank}")
            existing = (
                await session.execute(select(ReportExport).where(ReportExport.id == export_id))
            ).scalar_one_or_none()
            if existing:
                continue
            created_at = now - timedelta(minutes=rank + 500)
            file_path = None
            size_kb = None
            error_message = None
            if status == ReportExportStatus.READY:
                filename = f"seed_dashboard_backfill_status_{status.value}_{rank}.{export_format.lower()}"
                target_file = REPORT_DIR / filename
                target_file.write_text(_render_report_content(report_id, export_format), encoding="utf-8")
                file_path = str(target_file)
                size_kb = max(1, int(target_file.stat().st_size / 1024))
            elif status == ReportExportStatus.FAILED:
                error_message = "Coverage seeded failed export"
            session.add(
                ReportExport(
                    id=export_id,
                    report_id=report_id,
                    format=export_format,
                    status=status.value,
                    file_path=file_path,
                    size_kb=size_kb,
                    error_message=error_message,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    for report_format in ReportFormat:
        current = format_counts.get(report_format.value, 0)
        for rank in range(current + 1, target + 1):
            report_id = REPORT_IDS[rank % len(REPORT_IDS)]
            status = list(ReportExportStatus)[rank % len(ReportExportStatus)]
            export_id = _seed_id(f"coverage-report-backfill-format-{report_format.value}-{rank}")
            existing = (
                await session.execute(select(ReportExport).where(ReportExport.id == export_id))
            ).scalar_one_or_none()
            if existing:
                continue
            created_at = now - timedelta(minutes=rank + 700)
            file_path = None
            size_kb = None
            error_message = None
            if status == ReportExportStatus.READY:
                filename = f"seed_dashboard_backfill_format_{report_format.value.lower()}_{rank}.{report_format.value.lower()}"
                target_file = REPORT_DIR / filename
                target_file.write_text(_render_report_content(report_id, report_format.value), encoding="utf-8")
                file_path = str(target_file)
                size_kb = max(1, int(target_file.stat().st_size / 1024))
            elif status == ReportExportStatus.FAILED:
                error_message = "Coverage seeded failed export"
            session.add(
                ReportExport(
                    id=export_id,
                    report_id=report_id,
                    format=report_format.value,
                    status=status.value,
                    file_path=file_path,
                    size_kb=size_kb,
                    error_message=error_message,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    for report_id in REPORT_IDS:
        current = report_counts.get(report_id, 0)
        for rank in range(current + 1, target + 1):
            status = list(ReportExportStatus)[rank % len(ReportExportStatus)]
            export_format = list(ReportFormat)[rank % len(ReportFormat)].value
            export_id = _seed_id(f"coverage-report-backfill-report-{report_id}-{rank}")
            existing = (
                await session.execute(select(ReportExport).where(ReportExport.id == export_id))
            ).scalar_one_or_none()
            if existing:
                continue
            created_at = now - timedelta(minutes=rank + 900)
            file_path = None
            size_kb = None
            error_message = None
            if status == ReportExportStatus.READY:
                filename = f"seed_dashboard_backfill_report_{report_id}_{rank}.{export_format.lower()}"
                target_file = REPORT_DIR / filename
                target_file.write_text(_render_report_content(report_id, export_format), encoding="utf-8")
                file_path = str(target_file)
                size_kb = max(1, int(target_file.stat().st_size / 1024))
            elif status == ReportExportStatus.FAILED:
                error_message = "Coverage seeded failed export"
            session.add(
                ReportExport(
                    id=export_id,
                    report_id=report_id,
                    format=export_format,
                    status=status.value,
                    file_path=file_path,
                    size_kb=size_kb,
                    error_message=error_message,
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    await session.flush()


async def _ensure_order_export_job_coverage(session, user: User, target: int) -> None:
    rows = await session.execute(
        select(OrderExportJob.status, func.count(OrderExportJob.id)).group_by(OrderExportJob.status)
    )
    existing_statuses = {_value(status): int(count) for status, count in rows.all()}
    now = datetime.now(UTC)

    for idx, status_value in enumerate(OrderExportStatus):
        current = existing_statuses.get(status_value.value, 0)
        for rank in range(current + 1, target + 1):
            file_url = None
            error_message = None
            if status_value == OrderExportStatus.DONE:
                file_url = f"/uploads/reports/orders_export_seed_done_{rank}.csv"
            if status_value == OrderExportStatus.FAILED:
                error_message = "Coverage seeded failed order export job"

            job_id = _seed_id(f"coverage-order-export-job-{status_value.value}-{rank}")
            existing_job = (
                await session.execute(select(OrderExportJob).where(OrderExportJob.id == job_id))
            ).scalar_one_or_none()
            if existing_job:
                continue
            session.add(
                OrderExportJob(
                    id=job_id,
                    requested_by=user.id,
                    destination_email="owner@kinmel-test.local",
                    status=status_value,
                    filters_json='{"status":"completed"}',
                    file_url=file_url,
                    error_message=error_message,
                    created_at=now - timedelta(minutes=(idx * target) + rank),
                    updated_at=now - timedelta(minutes=(idx * target) + rank),
                )
            )

    await session.flush()


async def _ensure_pos_sale_status_coverage(
    session,
    user: User,
    product: Product | None,
    target: int,
) -> None:
    if not product:
        return

    location = (
        await session.execute(
            select(Location).where(Location.is_active == True).order_by(Location.code).limit(1)
        )
    ).scalar_one_or_none()
    if not location:
        return

    barcode_record = (
        await session.execute(
            select(ProductBarcode)
            .where(ProductBarcode.product_id == product.id)
            .order_by(ProductBarcode.is_primary.desc(), ProductBarcode.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    barcode = (
        barcode_record.barcode
        if barcode_record
        else (product.barcode or f"COVPOS{uuid5(NAMESPACE_DNS, product.sku).hex[:10].upper()}")
    )

    status_rows = await session.execute(
        select(PosSale.status, func.count(PosSale.id)).group_by(PosSale.status)
    )
    status_counts = {_value(status): int(count) for status, count in status_rows.all()}

    now = datetime.now(UTC)
    for idx, status_value in enumerate(PosSaleStatus):
        current = status_counts.get(status_value.value, 0)
        for rank in range(current + 1, target + 1):
            sale_id = _seed_id(f"coverage-pos-sale-{status_value.value}-{rank}")
            existing = (
                await session.execute(select(PosSale).where(PosSale.id == sale_id))
            ).scalar_one_or_none()
            if existing:
                continue

            if status_value == PosSaleStatus.RESERVED:
                reserved_until = now + timedelta(minutes=3)
            elif status_value == PosSaleStatus.EXPIRED:
                reserved_until = now - timedelta(minutes=5)
            else:
                reserved_until = now - timedelta(minutes=15)

            created_at = now - timedelta(minutes=(idx * target) + rank)
            sale = PosSale(
                id=sale_id,
                location_id=location.id,
                status=status_value,
                idempotency_key=f"seed-pos-{status_value.value}-{rank}",
                reserved_until=reserved_until,
                created_by=user.id,
                created_at=created_at,
                updated_at=created_at,
            )
            session.add(sale)
            session.add(
                PosSaleLine(
                    id=_seed_id(f"coverage-pos-sale-line-{status_value.value}-{rank}"),
                    sale_id=sale.id,
                    barcode=barcode,
                    sku=product.sku,
                    qty=1,
                    unit_price_at_sale=product.unit_price,
                    tax_rate_at_sale=product.tax_rate,
                    name_snapshot=product.name,
                    created_at=sale.created_at,
                    updated_at=sale.updated_at,
                )
            )

    await session.flush()


async def _ensure_notification_type_coverage(session, target: int) -> None:
    rows = await session.execute(
        select(Notification.type, func.count(Notification.id)).group_by(Notification.type)
    )
    type_counts = {_value(kind): int(count) for kind, count in rows.all()}
    now = datetime.now(UTC)

    for idx, notif_type in enumerate(NotificationType):
        current = type_counts.get(notif_type.value, 0)
        for rank in range(current + 1, target + 1):
            notif_id = _seed_id(f"coverage-notification-{notif_type.value}-{rank}")
            existing = (
                await session.execute(select(Notification).where(Notification.id == notif_id))
            ).scalar_one_or_none()
            if existing:
                continue
            created_at = now - timedelta(minutes=(idx * target) + rank + 120)
            session.add(
                Notification(
                    id=notif_id,
                    type=notif_type,
                    title=f"Coverage {notif_type.value.title()} Notification {rank}",
                    message=f"Seeded notification for type={notif_type.value} (#{rank}).",
                    source_label="Open notifications",
                    source_href="/dashboard/notifications",
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    await session.flush()


async def _ensure_owner_unread_notification(session) -> None:
    owner = (
        await session.execute(select(User).where(User.email == "owner@kinmel-test.local"))
    ).scalar_one_or_none()
    if not owner:
        return

    unread_count = int(
        (
            await session.execute(
                select(func.count(Notification.id))
                .select_from(Notification)
                .outerjoin(
                    NotificationRead,
                    and_(
                        NotificationRead.notification_id == Notification.id,
                        NotificationRead.user_id == owner.id,
                    ),
                )
                .where(NotificationRead.id.is_(None))
            )
        ).scalar_one()
        or 0
    )
    if unread_count > 0:
        return

    notif_id = _seed_id("coverage-owner-unread-notification")
    existing = (
        await session.execute(select(Notification).where(Notification.id == notif_id))
    ).scalar_one_or_none()
    if existing:
        return

    now = datetime.now(UTC)
    session.add(
        Notification(
            id=notif_id,
            type=NotificationType.ALERT,
            title="Coverage unread notification",
            message="Unread item seeded to validate unread counters.",
            source_label="Open notifications",
            source_href="/dashboard/notifications",
            created_at=now,
            updated_at=now,
        )
    )
    await session.flush()


async def ensure_coverage_completeness() -> None:
    async with async_session_factory() as session:
        user = await _ensure_user_minimums(session, TARGET_MIN_PER_TYPE)
        await _ensure_category_status_minimums(session, TARGET_MIN_PER_TYPE)
        await _ensure_product_status_minimums(session, TARGET_MIN_PER_TYPE)
        await _ensure_location_type_coverage(session, TARGET_MIN_PER_TYPE)
        product = await _ensure_product_barcode_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_inventory_state_minimums(session, TARGET_MIN_PER_TYPE)
        await _ensure_order_status_type_minimums(session, TARGET_MIN_PER_TYPE)
        await _ensure_movement_reason_coverage(session, user, TARGET_MIN_PER_TYPE)
        await _ensure_substitution_status_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_contact_channel_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_revenue_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_reports_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_order_export_job_coverage(session, user, TARGET_MIN_PER_TYPE)
        await _ensure_pos_sale_status_coverage(session, user, product, TARGET_MIN_PER_TYPE)
        await _ensure_notification_type_coverage(session, TARGET_MIN_PER_TYPE)
        await _ensure_owner_unread_notification(session)
        await session.commit()


async def print_coverage_summary() -> None:
    async with async_session_factory() as session:
        users = (await session.execute(select(User))).scalars().all()
        user_status_counts = {"active": 0, "invited": 0, "inactive": 0, "canceled": 0}
        for user in users:
            if user.is_active and user.is_verified:
                user_status_counts["active"] += 1
            elif user.is_active and not user.is_verified:
                user_status_counts["invited"] += 1
            elif (not user.is_active) and user.is_verified:
                user_status_counts["inactive"] += 1
            else:
                user_status_counts["canceled"] += 1

        role_rows = await session.execute(select(User.role, func.count(User.id)).group_by(User.role))
        user_role_counts = {_value(role): int(count) for role, count in role_rows.all()}
        user_role_counts = _ordered_counts(user_role_counts, [role.value for role in Role])

        product_rows = await session.execute(
            select(Product.status, func.count(Product.id)).group_by(Product.status)
        )
        product_status_counts = {_value(status): int(count) for status, count in product_rows.all()}
        product_status_counts = _ordered_counts(product_status_counts, _enum_values(ProductStatus))
        barcode_count = int(
            (await session.execute(select(func.count(ProductBarcode.id)))).scalar_one() or 0
        )

        category_rows = await session.execute(
            select(Category.status, func.count(Category.id)).group_by(Category.status)
        )
        category_status_counts = {_value(status): int(count) for status, count in category_rows.all()}
        category_status_counts = _ordered_counts(
            category_status_counts, _enum_values(CategoryStatus)
        )

        location_rows = await session.execute(
            select(Location.location_type, func.count(Location.id))
            .where(Location.is_active == True)
            .group_by(Location.location_type)
        )
        location_type_counts = {
            _value(location_type): int(count) for location_type, count in location_rows.all()
        }
        location_type_counts = _ordered_counts(
            location_type_counts, _enum_values(LocationType)
        )

        inventory_aggregate = await session.execute(
            select(
                func.count(InventoryItem.id),
                func.sum(case((InventoryItem.physical_stock == 0, 1), else_=0)),
                func.sum(case((InventoryItem.physical_stock <= InventoryItem.reorder_point, 1), else_=0)),
                func.sum(
                    case(
                        (
                            and_(
                                InventoryItem.physical_stock > 0,
                                InventoryItem.physical_stock <= InventoryItem.reorder_point,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(case((InventoryItem.physical_stock > InventoryItem.reorder_point, 1), else_=0)),
            )
        )
        (
            inventory_total,
            out_of_stock_count,
            below_threshold_count,
            low_stock_count,
            in_stock_count,
        ) = inventory_aggregate.one()
        out_of_stock_count = int(out_of_stock_count or 0)
        below_threshold_count = int(below_threshold_count or 0)
        low_stock_count = int(low_stock_count or 0)
        in_stock_count = int(in_stock_count or 0)

        now = datetime.now(UTC)
        batch_stats = await session.execute(
            select(
                func.count(InventoryBatch.id),
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.expiry_date >= now,
                                InventoryBatch.expiry_date <= now + timedelta(days=7),
                                InventoryBatch.quantity > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                func.sum(
                    case(
                        (
                            and_(
                                InventoryBatch.expiry_date < now,
                                InventoryBatch.quantity > 0,
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
            )
        )
        batch_total, expiring_soon_count, expired_batch_count = batch_stats.one()
        batch_total = int(batch_total or 0)
        expiring_soon_count = int(expiring_soon_count or 0)
        expired_batch_count = int(expired_batch_count or 0)

        movement_type_rows = await session.execute(
            select(StockMovement.movement_type, func.count(StockMovement.id)).group_by(
                StockMovement.movement_type
            )
        )
        movement_type_counts = {
            _value(movement_type): int(count)
            for movement_type, count in movement_type_rows.all()
        }
        movement_type_counts = _ordered_counts(
            movement_type_counts, _enum_values(MovementType)
        )

        movement_reason_rows = await session.execute(
            select(StockMovement.reason, func.count(StockMovement.id)).group_by(StockMovement.reason)
        )
        movement_reason_counts = {
            _value(reason): int(count) for reason, count in movement_reason_rows.all()
        }
        movement_reason_counts = _ordered_counts(
            movement_reason_counts, _enum_values(MovementReason)
        )

        order_rows = await session.execute(
            select(Order.status, func.count(Order.id)).group_by(Order.status)
        )
        order_status_counts = {_value(status): int(count) for status, count in order_rows.all()}
        order_status_counts = _ordered_counts(order_status_counts, _enum_values(OrderStatus))

        order_type_rows = await session.execute(
            select(Order.order_type, func.count(Order.id)).group_by(Order.order_type)
        )
        order_type_counts = {_value(order_type): int(count) for order_type, count in order_type_rows.all()}
        order_type_counts = _ordered_counts(order_type_counts, _enum_values(OrderType))

        substitution_rows = await session.execute(
            select(OrderItemSubstitution.status, func.count(OrderItemSubstitution.id)).group_by(
                OrderItemSubstitution.status
            )
        )
        substitution_status_counts = {
            _value(status): int(count) for status, count in substitution_rows.all()
        }
        substitution_status_counts = _ordered_counts(
            substitution_status_counts, _enum_values(SubstitutionStatus)
        )

        channel_rows = await session.execute(
            select(OrderContactAttempt.channel, func.count(OrderContactAttempt.id)).group_by(
                OrderContactAttempt.channel
            )
        )
        contact_channel_counts = {
            _value(channel): int(count) for channel, count in channel_rows.all()
        }
        contact_channel_counts = _ordered_counts(
            contact_channel_counts, _enum_values(ContactChannel)
        )

        order_export_rows = await session.execute(
            select(OrderExportJob.status, func.count(OrderExportJob.id)).group_by(OrderExportJob.status)
        )
        order_export_status_counts = {
            _value(status): int(count) for status, count in order_export_rows.all()
        }
        order_export_status_counts = _ordered_counts(
            order_export_status_counts, _enum_values(OrderExportStatus)
        )

        payment_rows = await session.execute(
            select(RevenuePayment.status, func.count(RevenuePayment.id)).group_by(RevenuePayment.status)
        )
        payment_status_counts = {_value(status): int(count) for status, count in payment_rows.all()}
        payment_status_counts = _ordered_counts(payment_status_counts, _enum_values(PaymentStatus))

        payment_method_rows = await session.execute(
            select(RevenuePayment.method, func.count(RevenuePayment.id)).group_by(RevenuePayment.method)
        )
        payment_method_counts = {_value(method): int(count) for method, count in payment_method_rows.all()}
        payment_method_counts = _ordered_counts(payment_method_counts, _enum_values(PaymentMethod))

        payout_rows = await session.execute(
            select(RevenuePayout.status, func.count(RevenuePayout.id)).group_by(RevenuePayout.status)
        )
        payout_status_counts = {_value(status): int(count) for status, count in payout_rows.all()}
        payout_status_counts = _ordered_counts(payout_status_counts, _enum_values(PayoutStatus))

        adjustment_rows = await session.execute(
            select(RevenueAdjustment.adjustment_type, func.count(RevenueAdjustment.id)).group_by(
                RevenueAdjustment.adjustment_type
            )
        )
        adjustment_type_counts = {
            _value(adjustment_type): int(count) for adjustment_type, count in adjustment_rows.all()
        }
        adjustment_type_counts = _ordered_counts(
            adjustment_type_counts, _enum_values(AdjustmentType)
        )

        export_rows = await session.execute(
            select(ReportExport.status, func.count(ReportExport.id)).group_by(ReportExport.status)
        )
        export_status_counts = {_value(status): int(count) for status, count in export_rows.all()}
        export_status_counts = _ordered_counts(
            export_status_counts, _enum_values(ReportExportStatus)
        )

        export_format_rows = await session.execute(
            select(ReportExport.format, func.count(ReportExport.id)).group_by(ReportExport.format)
        )
        export_format_counts = {
            _value(export_format): int(count) for export_format, count in export_format_rows.all()
        }
        export_format_counts = _ordered_counts(export_format_counts, _enum_values(ReportFormat))

        report_id_rows = await session.execute(
            select(ReportExport.report_id, func.count(ReportExport.id)).group_by(ReportExport.report_id)
        )
        report_id_counts = {_value(report_id): int(count) for report_id, count in report_id_rows.all()}
        report_id_counts = _ordered_counts(report_id_counts, list(REPORT_IDS))

        notification_rows = await session.execute(
            select(Notification.type, func.count(Notification.id)).group_by(Notification.type)
        )
        notification_type_counts = {_value(kind): int(count) for kind, count in notification_rows.all()}
        notification_type_counts = _ordered_counts(
            notification_type_counts, _enum_values(NotificationType)
        )

        read_total = int(
            (await session.execute(select(func.count(NotificationRead.id)))).scalar_one() or 0
        )

        owner = (
            await session.execute(select(User).where(User.email == "owner@kinmel-test.local"))
        ).scalar_one_or_none()
        owner_unread = 0
        if owner:
            owner_unread = int(
                (
                    await session.execute(
                        select(func.count(Notification.id))
                        .select_from(Notification)
                        .outerjoin(
                            NotificationRead,
                            and_(
                                NotificationRead.notification_id == Notification.id,
                                NotificationRead.user_id == owner.id,
                            ),
                        )
                        .where(NotificationRead.id.is_(None))
                    )
                ).scalar_one()
                or 0
            )

        pos_rows = await session.execute(
            select(PosSale.status, func.count(PosSale.id)).group_by(PosSale.status)
        )
        pos_status_counts = {_value(status): int(count) for status, count in pos_rows.all()}
        pos_status_counts = _ordered_counts(pos_status_counts, _enum_values(PosSaleStatus))

        customer_status_counts: dict[str, int] = {}
        customer_segment_counts: dict[str, int] = {}
        for customer in _CUSTOMERS:
            status_key = str(customer.get("status", "unknown"))
            segment_key = str(customer.get("segment", "unknown"))
            customer_status_counts[status_key] = customer_status_counts.get(status_key, 0) + 1
            customer_segment_counts[segment_key] = customer_segment_counts.get(segment_key, 0) + 1

        print("\n=== Dashboard Data Coverage Summary ===")
        print(f"Target Per Type/Status: >= {TARGET_MIN_PER_TYPE}")
        print(
            "Users:",
            f"total={len(users)}",
            f"by_role={user_role_counts}",
            f"active={user_status_counts['active']}",
            f"invited={user_status_counts['invited']}",
            f"inactive={user_status_counts['inactive']}",
            f"canceled={user_status_counts['canceled']}",
            f"below_target_roles={_below_target_keys(user_role_counts, TARGET_MIN_PER_TYPE) or 'none'}",
            f"below_target_statuses={_below_target_keys(user_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Products:",
            f"total={sum(product_status_counts.values())}",
            f"by_status={product_status_counts}",
            f"barcodes={barcode_count}",
            f"below_target_statuses={_below_target_keys(product_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Categories:",
            f"total={sum(category_status_counts.values())}",
            f"by_status={category_status_counts}",
            f"below_target_statuses={_below_target_keys(category_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Locations:",
            f"by_type={location_type_counts}",
            f"below_target_types={_below_target_keys(location_type_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Inventory:",
            f"total_items={int(inventory_total or 0)}",
            f"in_stock={in_stock_count}",
            f"low_stock={low_stock_count}",
            f"out_of_stock={out_of_stock_count}",
            f"below_threshold={below_threshold_count}",
            f"batches={batch_total}",
            f"expiring_7d={expiring_soon_count}",
            f"expired_batches={expired_batch_count}",
            f"below_target_states={_below_target_keys({'in_stock': in_stock_count, 'low_stock': low_stock_count, 'out_of_stock': out_of_stock_count}, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Inventory Movements:",
            f"by_type={movement_type_counts}",
            f"below_target_types={_below_target_keys(movement_type_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Inventory Reasons:",
            f"by_reason={movement_reason_counts}",
            f"below_target_reasons={_below_target_keys(movement_reason_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Orders:",
            f"total={sum(order_status_counts.values())}",
            f"by_status={order_status_counts}",
            f"by_type={order_type_counts}",
            f"below_target_statuses={_below_target_keys(order_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
            f"below_target_types={_below_target_keys(order_type_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Substitutions:",
            f"by_status={substitution_status_counts}",
            f"below_target_statuses={_below_target_keys(substitution_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Contact Attempts:",
            f"by_channel={contact_channel_counts}",
            f"below_target_channels={_below_target_keys(contact_channel_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Order Export Jobs:",
            f"by_status={order_export_status_counts}",
            f"below_target_statuses={_below_target_keys(order_export_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Revenue Payments:",
            f"total={sum(payment_status_counts.values())}",
            f"by_status={payment_status_counts}",
            f"by_method={payment_method_counts}",
            f"below_target_statuses={_below_target_keys(payment_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
            f"below_target_methods={_below_target_keys(payment_method_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Revenue Payouts:",
            f"by_status={payout_status_counts}",
            f"below_target_statuses={_below_target_keys(payout_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Revenue Adjustments:",
            f"by_type={adjustment_type_counts}",
            f"below_target_types={_below_target_keys(adjustment_type_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Report Exports:",
            f"total={sum(export_status_counts.values())}",
            f"by_status={export_status_counts}",
            f"by_format={export_format_counts}",
            f"by_report={report_id_counts}",
            f"below_target_statuses={_below_target_keys(export_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
            f"below_target_formats={_below_target_keys(export_format_counts, TARGET_MIN_PER_TYPE) or 'none'}",
            f"below_target_report_ids={_below_target_keys(report_id_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Notifications:",
            f"total={sum(notification_type_counts.values())}",
            f"by_type={notification_type_counts}",
            f"read_records={read_total}",
            f"owner_unread={owner_unread}",
            f"below_target_types={_below_target_keys(notification_type_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print(
            "Customers:",
            "module uses in-memory repository (not DB table).",
            f"total={len(_CUSTOMERS)}",
            f"by_status={customer_status_counts}",
            f"by_segment={customer_segment_counts}",
        )
        print(
            "POS Sales:",
            f"by_status={pos_status_counts}",
            f"below_target_statuses={_below_target_keys(pos_status_counts, TARGET_MIN_PER_TYPE) or 'none'}",
        )
        print("======================================\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed complete dashboard test data.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing seeded data before reseeding.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt for destructive clear.",
    )
    return parser.parse_args()


async def _run_async_dashboard_steps() -> None:
    try:
        await ensure_coverage_completeness()
        await print_coverage_summary()
    finally:
        # Explicitly dispose pooled asyncpg connections before loop shutdown.
        await close_db()


def main() -> int:
    args = parse_args()

    try:
        if args.clear:
            clear_cmd = ["scripts/seed_data.py", "--clear"]
            if args.force:
                clear_cmd.append("--force")
            run_step("clear", clear_cmd)

        for name, command in SEED_STEPS:
            run_step(name, command)

        print(
            f"-> Running coverage completion: ensuring every dashboard data type has at least {TARGET_MIN_PER_TYPE} records"
        )
        asyncio.run(_run_async_dashboard_steps())
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
