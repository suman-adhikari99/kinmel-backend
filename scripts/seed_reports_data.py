#!/usr/bin/env python3
"""
Seed report-related dummy data.

Creates:
- Recent orders (used by report summary and sales/orders reports)
- Report exports with ready/processing/failed statuses

Usage:
  python scripts/seed_reports_data.py
  python scripts/seed_reports_data.py --orders
  python scripts/seed_reports_data.py --exports
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

from sqlalchemy import select, func

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.modules.orders.models import Order, OrderStatus, OrderType
from src.modules.reports.models import ReportExport


EXPORT_DIR = Path("uploads/reports")
SEED_EXPORT_PREFIX = "seed_report_"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def seed_orders(session, *, target_recent: int = 20) -> int:
    now = datetime.now(UTC)
    since = now - timedelta(days=30)

    existing_count = await session.execute(
        select(func.count()).select_from(Order).where(Order.created_at >= since)
    )
    current = int(existing_count.scalar_one())
    to_create = max(0, target_recent - current)
    if to_create == 0:
        return 0

    created = 0
    for idx in range(to_create):
        created_at = now - timedelta(days=to_create - idx)
        order_type = OrderType.DELIVERY if idx % 2 else OrderType.PICKUP
        delivery_fee = Decimal("6.00") if order_type == OrderType.DELIVERY else Decimal("0.00")
        subtotal = Decimal("25.00") + Decimal(idx * 3)
        gst = _money(subtotal * Decimal("0.10"))
        total = _money(subtotal + gst + delivery_fee)
        order_id = str(uuid5(NAMESPACE_DNS, f"seed-report-order-{idx + 1}"))

        existing = await session.execute(select(Order.id).where(Order.id == order_id))
        if existing.scalar_one_or_none():
            continue

        order = Order(
            id=order_id,
            order_type=order_type,
            status=OrderStatus.COMPLETED if idx % 3 else OrderStatus.READY,
            time_slot="09:00-11:00" if order_type == OrderType.DELIVERY else "10:00-12:00",
            customer_name=f"Report Seed Customer {idx + 1}",
            customer_phone=f"+61 400 100 {idx:03d}",
            customer_email=f"report-seed-{idx + 1}@example.com",
            delivery_address="123 Seed St, Sydney NSW 2000" if order_type == OrderType.DELIVERY else None,
            delivery_suburb="Sydney" if order_type == OrderType.DELIVERY else None,
            subtotal=subtotal,
            gst=gst,
            delivery_fee=delivery_fee,
            total=total,
            notes="Seeded for reports",
            has_substitutions=False,
            created_at=created_at,
            updated_at=created_at,
            delivered_at=created_at if order_type == OrderType.DELIVERY else None,
        )
        session.add(order)
        created += 1

    await session.flush()
    return created


def _build_csv(rows: list[dict[str, str | int | float]]) -> str:
    if not rows:
        return ""
    headers = rows[0].keys()
    lines = [",".join(headers)]
    for row in rows:
        lines.append(",".join(str(row[h]) for h in headers))
    return "\n".join(lines)


async def seed_exports(session) -> int:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    seeds = [
        {
            "report_id": "sales",
            "format": "CSV",
            "status": "ready",
            "created_at": now - timedelta(days=1),
        },
        {
            "report_id": "orders",
            "format": "CSV",
            "status": "ready",
            "created_at": now - timedelta(days=2),
        },
        {
            "report_id": "sales",
            "format": "XLSX",
            "status": "ready",
            "created_at": now - timedelta(days=3),
        },
        {
            "report_id": "orders",
            "format": "PDF",
            "status": "ready",
            "created_at": now - timedelta(days=4),
        },
        {
            "report_id": "sales",
            "format": "CSV",
            "status": "processing",
            "created_at": now - timedelta(hours=6),
        },
        {
            "report_id": "orders",
            "format": "CSV",
            "status": "failed",
            "created_at": now - timedelta(hours=3),
        },
    ]

    created = 0
    for seed in seeds:
        stamp = seed["created_at"].strftime("%Y%m%d")
        file_name = f"{SEED_EXPORT_PREFIX}{seed['report_id']}_{stamp}.{seed['format'].lower()}"
        file_path = str(EXPORT_DIR / file_name)

        existing = await session.execute(
            select(ReportExport.id).where(ReportExport.file_path == file_path)
        )
        if existing.scalar_one_or_none():
            continue

        size_kb = None
        path_value = None
        error_message = None
        if seed["status"] == "ready":
            if seed["report_id"] == "sales":
                rows = [
                    {
                        "date": (now - timedelta(days=idx)).date().isoformat(),
                        "total_sales": 120 + idx * 8,
                        "gst": 12 + idx,
                        "orders": 4 + idx,
                    }
                    for idx in range(5)
                ]
            else:
                rows = [
                    {
                        "order_id": f"ORD-{1000 + idx}",
                        "total": 45 + idx * 3,
                        "status": "completed",
                        "customer": f"Customer {idx + 1}",
                    }
                    for idx in range(5)
                ]

            content = _build_csv(rows)
            if seed["format"] == "PDF":
                content = f"Report Export\n\n{content}"
            (EXPORT_DIR / file_name).write_text(content, encoding="utf-8")
            size_kb = max(1, int((EXPORT_DIR / file_name).stat().st_size / 1024))
            path_value = file_path
        elif seed["status"] == "failed":
            error_message = "Seeded export failed"

        export = ReportExport(
            report_id=seed["report_id"],
            format=seed["format"],
            status=seed["status"],
            file_path=path_value,
            size_kb=size_kb,
            error_message=error_message,
            created_at=seed["created_at"],
            updated_at=seed["created_at"],
        )
        session.add(export)
        created += 1

    await session.flush()
    return created


async def run(seed_orders_flag: bool, seed_exports_flag: bool) -> None:
    async with async_session_factory() as session:
        created_orders = 0
        created_exports = 0
        if seed_orders_flag:
            created_orders = await seed_orders(session)
        if seed_exports_flag:
            created_exports = await seed_exports(session)
        await session.commit()
        print(f"Seeded orders: {created_orders}, exports: {created_exports}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed report-related data.")
    parser.add_argument("--orders", action="store_true", help="Seed recent orders only")
    parser.add_argument("--exports", action="store_true", help="Seed report exports only")
    args = parser.parse_args()

    seed_orders_flag = args.orders or (not args.orders and not args.exports)
    seed_exports_flag = args.exports or (not args.orders and not args.exports)
    asyncio.run(run(seed_orders_flag, seed_exports_flag))


if __name__ == "__main__":
    main()
