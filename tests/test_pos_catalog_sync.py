"""
POS Catalog Sync Tests
----------------------
Verify POS catalog bootstrap and change sync behavior.
"""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import status

from src.api.deps import get_db
from src.main import app
from src.modules.products.models import Product, ProductBarcode, ProductStatus


@pytest.mark.asyncio
async def test_pos_catalog_bootstrap_returns_active_products(
    async_client,
    test_db,
    staff_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        product = Product(
            sku="POS-BOOT-1",
            name="POS Boot Product",
            category="Dairy",
            unit_price=Decimal("3.50"),
            tax_rate=Decimal("0.10"),
            status=ProductStatus.ACTIVE,
        )
        archived = Product(
            sku="POS-BOOT-ARCH",
            name="Archived Product",
            category="Dairy",
            unit_price=Decimal("2.00"),
            tax_rate=Decimal("0.10"),
            status=ProductStatus.ARCHIVED,
        )
        test_db.add_all([product, archived])
        await test_db.flush()

        test_db.add_all(
            [
                ProductBarcode(
                    product_id=product.id,
                    barcode="11111111",
                    is_primary=True,
                ),
                ProductBarcode(
                    product_id=product.id,
                    barcode="22222222",
                    is_primary=False,
                ),
            ]
        )
        product.barcode = "11111111"
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/pos/catalog/bootstrap",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["sync_token"]
        products = data["products"]
        assert len(products) == 1
        item = products[0]
        assert item["sku"] == "POS-BOOT-1"
        assert item["primary_barcode"] == "11111111"
        assert item["barcodes"] == ["11111111", "22222222"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pos_catalog_changes_only_changed_products(
    async_client,
    test_db,
    staff_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        base_time = datetime(2024, 1, 1, 0, 0, 0)
        product_a = Product(
            sku="POS-CHG-A",
            name="Product A",
            category="Snacks",
            unit_price=Decimal("1.50"),
            tax_rate=Decimal("0.05"),
            status=ProductStatus.ACTIVE,
            updated_at=base_time,
        )
        product_b = Product(
            sku="POS-CHG-B",
            name="Product B",
            category="Snacks",
            unit_price=Decimal("2.50"),
            tax_rate=Decimal("0.05"),
            status=ProductStatus.ACTIVE,
            updated_at=base_time,
        )
        test_db.add_all([product_a, product_b])
        await test_db.commit()

        since = (base_time + timedelta(seconds=1)).isoformat()
        product_a.name = "Product A Updated"
        product_a.updated_at = base_time + timedelta(seconds=2)
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/pos/catalog/changes",
            params={"since": since},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        changed_skus = {item["sku"] for item in data["changed"]}
        assert "POS-CHG-A" in changed_skus
        assert "POS-CHG-B" not in changed_skus
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pos_catalog_changes_includes_barcode_updates(
    async_client,
    test_db,
    staff_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        base_time = datetime(2024, 1, 2, 0, 0, 0)
        product = Product(
            sku="POS-BC-1",
            name="Barcode Update Product",
            category="Frozen",
            unit_price=Decimal("4.00"),
            tax_rate=Decimal("0.12"),
            status=ProductStatus.ACTIVE,
            updated_at=base_time,
        )
        test_db.add(product)
        await test_db.flush()
        test_db.add(
            ProductBarcode(
                product_id=product.id,
                barcode="33333333",
                is_primary=True,
                updated_at=base_time,
            )
        )
        product.barcode = "33333333"
        await test_db.commit()

        since = (base_time + timedelta(seconds=1)).isoformat()
        test_db.add(
            ProductBarcode(
                product_id=product.id,
                barcode="44444444",
                is_primary=False,
                updated_at=base_time + timedelta(seconds=2),
            )
        )
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/pos/catalog/changes",
            params={"since": since},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        changed_skus = {item["sku"] for item in data["changed"]}
        assert "POS-BC-1" in changed_skus
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pos_catalog_changes_includes_deleted_skus(
    async_client,
    test_db,
    staff_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        base_time = datetime(2024, 1, 3, 0, 0, 0)
        product = Product(
            sku="POS-DEL-1",
            name="Deactivated Product",
            category="Bakery",
            unit_price=Decimal("2.75"),
            tax_rate=Decimal("0.08"),
            status=ProductStatus.ACTIVE,
            updated_at=base_time,
        )
        test_db.add(product)
        await test_db.commit()

        since = (base_time + timedelta(seconds=1)).isoformat()
        product.status = ProductStatus.ARCHIVED
        product.updated_at = base_time + timedelta(seconds=2)
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/pos/catalog/changes",
            params={"since": since},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "POS-DEL-1" in data["deleted_skus"]
        changed_skus = {item["sku"] for item in data["changed"]}
        assert "POS-DEL-1" not in changed_skus
    finally:
        app.dependency_overrides.clear()
