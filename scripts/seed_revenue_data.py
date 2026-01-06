#!/usr/bin/env python3
"""
Seed revenue data (business profile, payments, payouts, adjustments).

Usage:
  python scripts/seed_revenue_data.py
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
from src.modules.orders.models import Order, OrderStatus, OrderType
from src.modules.revenue.models import (
    AdjustmentType,
    BusinessProfile,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    RevenueAdjustment,
    RevenuePayment,
    RevenuePayout,
)


async def ensure_orders(session) -> list[Order]:
    orders = (await session.execute(select(Order))).scalars().all()
    if orders:
        return orders

    now = datetime.now(UTC)
    created = []
    for idx in range(3):
        order_id = str(uuid5(NAMESPACE_DNS, f"seed-revenue-order-{idx + 1}"))
        order = Order(
            id=order_id,
            order_type=OrderType.DELIVERY if idx % 2 else OrderType.PICKUP,
            status=OrderStatus.COMPLETED,
            time_slot="09:00-11:00",
            customer_name=f"Revenue Seed {idx + 1}",
            customer_phone=f"+61 400 300 {idx:03d}",
            customer_email=f"revenue-seed-{idx + 1}@example.com",
            delivery_address="1 Revenue Lane, Sydney NSW 2000" if idx % 2 else None,
            delivery_suburb="Sydney" if idx % 2 else None,
            subtotal=Decimal("40.00") + Decimal(idx * 5),
            gst=Decimal("4.00") + Decimal(idx),
            delivery_fee=Decimal("6.00") if idx % 2 else Decimal("0.00"),
            total=Decimal("50.00") + Decimal(idx * 6),
            notes="Seed order for revenue data",
            has_substitutions=False,
            created_at=now - timedelta(days=7 - idx),
            updated_at=now - timedelta(days=7 - idx),
            delivered_at=now - timedelta(days=6 - idx),
        )
        session.add(order)
        created.append(order)
    await session.flush()
    return created


async def seed_revenue() -> None:
    async with async_session_factory() as session:
        orders = await ensure_orders(session)

        existing_profile = await session.execute(select(BusinessProfile))
        if not existing_profile.scalars().first():
            profile = BusinessProfile(
                legal_name="Kinmel Grocery Pty Ltd",
                abn="12 345 678 901",
                gst_registered=True,
                gst_rate="10%",
                store_address="123 Market St, Sydney NSW 2000",
                contact_email="finance@kinmel-test.local",
                contact_phone="+61 2 9000 0000",
                bank_masked="**** 4321",
                payout_frequency="Weekly",
                processor="Stripe",
            )
            session.add(profile)

        payment_variants = [
            (PaymentMethod.CREDIT_CARD, PaymentStatus.COMPLETED),
            (PaymentMethod.DEBIT_CARD, PaymentStatus.REFUNDED),
            (PaymentMethod.CASH, PaymentStatus.FAILED),
        ]
        created_payments = 0
        for order, variant in zip(orders, payment_variants, strict=False):
            existing = await session.execute(
                select(RevenuePayment).where(RevenuePayment.order_id == order.id)
            )
            if existing.scalar_one_or_none():
                continue
            method, status = variant
            payment = RevenuePayment(
                order_id=order.id,
                method=method,
                status=status,
                amount=order.total,
                created_at=order.created_at + timedelta(hours=1),
                updated_at=order.created_at + timedelta(hours=1),
            )
            session.add(payment)
            created_payments += 1

        payout_entries = [
            ("2025-02-10T09:00:00Z", PayoutStatus.COMPLETED, Decimal("1200.00")),
            ("2025-02-17T09:00:00Z", PayoutStatus.PENDING, Decimal("980.00")),
        ]
        created_payouts = 0
        for payout_at, status, amount in payout_entries:
            existing = await session.execute(
                select(RevenuePayout).where(RevenuePayout.payout_at == payout_at)
            )
            if existing.scalar_one_or_none():
                continue
            payout = RevenuePayout(
                payout_at=payout_at,
                status=status,
                amount=amount,
            )
            session.add(payout)
            created_payouts += 1

        adjustment_entries = [
            (AdjustmentType.PLATFORM_FEE, Decimal("45.00"), "Seed platform fee"),
            (AdjustmentType.REFUND, Decimal("20.00"), "Seed customer refund"),
            (AdjustmentType.DISPUTE, Decimal("15.00"), "Seed dispute hold"),
        ]
        created_adjustments = 0
        for adjustment_type, amount, notes in adjustment_entries:
            existing = await session.execute(
                select(RevenueAdjustment).where(RevenueAdjustment.notes == notes)
            )
            if existing.scalar_one_or_none():
                continue
            adjustment = RevenueAdjustment(
                adjustment_type=adjustment_type,
                amount=amount,
                notes=notes,
            )
            session.add(adjustment)
            created_adjustments += 1

        await session.commit()
        print(
            "Seeded revenue: "
            f"{created_payments} payments, {created_payouts} payouts, {created_adjustments} adjustments."
        )


def main() -> None:
    asyncio.run(seed_revenue())


if __name__ == "__main__":
    main()
