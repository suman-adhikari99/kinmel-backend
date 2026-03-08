#!/usr/bin/env python3
"""
Normalize product/category images so UI never depends on external URLs.

Usage:
  python scripts/fix_catalog_images.py
"""

from __future__ import annotations

import asyncio
import base64
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.database import async_session_factory
from src.modules.products.models import Category, Product


PLACEHOLDER_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)

CATEGORY_UPLOAD_DIR = PROJECT_ROOT / "uploads" / "categories"
PRODUCT_UPLOAD_DIR = PROJECT_ROOT / "uploads" / "products"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


def _extract_upload_path(image_url: str | None) -> Path | None:
    if not image_url:
        return None

    parsed = urlparse(image_url)
    path = parsed.path if parsed.scheme else image_url
    if not path:
        return None

    normalized = path if path.startswith("/") else f"/{path}"
    if not normalized.startswith("/uploads/"):
        return None

    return PROJECT_ROOT / normalized.lstrip("/")


def _is_valid_local_file(path: Path | None) -> bool:
    return bool(path and path.exists() and path.is_file() and path.stat().st_size > 0)


def _ensure_placeholder(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not _is_valid_local_file(path):
        path.write_bytes(PLACEHOLDER_PNG_BYTES)


async def normalize_catalog_images() -> None:
    CATEGORY_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    PRODUCT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    async with async_session_factory() as session:
        categories = (await session.execute(select(Category))).scalars().all()
        products = (await session.execute(select(Product))).scalars().all()

        category_updates = 0
        product_updates = 0

        for category in categories:
            local_path = _extract_upload_path(category.image_url)
            valid_local = _is_valid_local_file(local_path)
            external = bool(category.image_url and category.image_url.startswith(("http://", "https://")))

            if valid_local:
                file_name = local_path.name
                if category.image_file != file_name:
                    category.image_file = file_name
                    category_updates += 1
                if category.image_url != f"/uploads/categories/{file_name}":
                    category.image_url = f"/uploads/categories/{file_name}"
                    category_updates += 1
                continue

            if external or not valid_local:
                file_name = category.image_file or f"seed-category-{_slugify(category.name)}.png"
                file_name = Path(file_name).name or f"seed-category-{_slugify(category.name)}.png"
                target = CATEGORY_UPLOAD_DIR / file_name
                _ensure_placeholder(target)

                next_url = f"/uploads/categories/{file_name}"
                if category.image_file != file_name:
                    category.image_file = file_name
                    category_updates += 1
                if category.image_url != next_url:
                    category.image_url = next_url
                    category_updates += 1

        for product in products:
            local_path = _extract_upload_path(product.image_url)
            valid_local = _is_valid_local_file(local_path)
            external = bool(product.image_url and product.image_url.startswith(("http://", "https://")))

            if valid_local:
                file_name = local_path.name
                if product.image_file != file_name:
                    product.image_file = file_name
                    product_updates += 1
                if product.image_url != f"/uploads/products/{file_name}":
                    product.image_url = f"/uploads/products/{file_name}"
                    product_updates += 1
                continue

            if external or not valid_local:
                file_name = product.image_file or f"seed-product-{_slugify(product.sku)}.png"
                file_name = Path(file_name).name or f"seed-product-{_slugify(product.sku)}.png"
                target = PRODUCT_UPLOAD_DIR / file_name
                _ensure_placeholder(target)

                next_url = f"/uploads/products/{file_name}"
                if product.image_file != file_name:
                    product.image_file = file_name
                    product_updates += 1
                if product.image_url != next_url:
                    product.image_url = next_url
                    product_updates += 1

        await session.commit()

    print(
        "Catalog image normalization complete:",
        f"category_updates={category_updates}",
        f"product_updates={product_updates}",
    )


def main() -> None:
    asyncio.run(normalize_catalog_images())


if __name__ == "__main__":
    main()

