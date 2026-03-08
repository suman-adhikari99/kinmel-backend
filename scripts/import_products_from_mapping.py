#!/usr/bin/env python3
"""
Import products from a barcode mapping CSV.

Expected columns: Barcode, Product Name, Price, SKU(optional)
Usage:
  python scripts/import_products_from_mapping.py path/to/file.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import os
import sys
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.core.database import async_session_factory
from src.modules.products.models import DEFAULT_CATEGORY, Product, ProductBarcode, ProductStatus


async def import_products_from_mapping(
    session: AsyncSession,
    csv_path: str,
) -> dict[str, int]:
    created = 0
    updated = 0
    unchanged = 0
    barcodes_added = 0
    skipped = 0
    processed = 0

    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            barcode = (row.get("Barcode") or "").strip()
            name = (row.get("Product Name") or "").strip()
            price_raw = (row.get("Price") or "").strip()
            sku_raw = (row.get("SKU") or "").strip()

            if not barcode or not name or not price_raw:
                skipped += 1
                continue

            try:
                price = Decimal(str(price_raw))
            except Exception:
                skipped += 1
                continue

            processed += 1
            sku = (sku_raw or f"AUTO-{barcode}").upper().strip()

            barcode_result = await session.execute(
                select(ProductBarcode)
                .options(joinedload(ProductBarcode.product))
                .where(ProductBarcode.barcode == barcode)
            )
            barcode_record = barcode_result.scalar_one_or_none()

            product = barcode_record.product if barcode_record else None
            if not product:
                sku_result = await session.execute(
                    select(Product).where(Product.sku == sku)
                )
                product = sku_result.scalar_one_or_none()

            created_row = False
            changed = False

            if not product:
                product = Product(
                    sku=sku,
                    name=name,
                    unit_price=price,
                    category=DEFAULT_CATEGORY,
                    tax_rate=Decimal("0.0"),
                    status=ProductStatus.ACTIVE,
                )
                session.add(product)
                await session.flush()
                created += 1
                created_row = True

            if product.name != name:
                product.name = name
                changed = True
            if product.unit_price != price:
                product.unit_price = price
                changed = True

            if not barcode_record:
                existing_count = await session.scalar(
                    select(func.count())
                    .select_from(ProductBarcode)
                    .where(ProductBarcode.product_id == product.id)
                )
                is_primary = existing_count == 0
                session.add(
                    ProductBarcode(
                        product_id=product.id,
                        barcode=barcode,
                        is_primary=is_primary,
                    )
                )
                if is_primary:
                    product.barcode = barcode
                barcodes_added += 1

            if not created_row:
                if changed:
                    updated += 1
                elif barcode_record is not None:
                    unchanged += 1

    await session.commit()

    products_total = await session.scalar(select(func.count()).select_from(Product)) or 0
    barcodes_total = await session.scalar(select(func.count()).select_from(ProductBarcode)) or 0

    return {
        "processed": processed,
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "barcodes_added": barcodes_added,
        "skipped": skipped,
        "products_total": int(products_total),
        "barcodes_total": int(barcodes_total),
    }


async def run_import(csv_path: str) -> dict[str, int]:
    async with async_session_factory() as session:
        return await import_products_from_mapping(session, csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import products from barcode mapping CSV")
    parser.add_argument("csv_path", help="Path to CSV file")
    args = parser.parse_args()

    summary = asyncio.run(run_import(args.csv_path))
    print(
        "Import complete. "
        f"processed={summary['processed']} "
        f"created={summary['created']} "
        f"updated={summary['updated']} "
        f"unchanged={summary['unchanged']} "
        f"barcodes_added={summary['barcodes_added']} "
        f"skipped={summary['skipped']} "
        f"products_total={summary['products_total']} "
        f"barcodes_total={summary['barcodes_total']}"
    )


if __name__ == "__main__":
    main()
