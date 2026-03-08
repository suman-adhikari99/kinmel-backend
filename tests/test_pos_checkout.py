"""
POS Checkout Tests
------------------
Validate POS reservation, commit, cancel, and idempotency behavior.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import status
from sqlalchemy import select, func

from src.api.deps import get_db
from src.main import app
from src.modules.inventory.models import InventoryItem, Location, LocationType
from src.modules.pos.models import PosSale, PosSaleStatus
from src.modules.pos.service import pos_service
from src.modules.products.models import Product, ProductBarcode, ProductStatus


async def seed_pos_inventory(
    test_db,
    *,
    sku: str,
    barcode: str,
    qty: int,
    unit_price: Decimal,
    tax_rate: Decimal,
) -> tuple[Location, Product]:
    location = Location(
        code="FLOOR-01",
        name="Floor 01",
        location_type=LocationType.FLOOR,
    )
    product = Product(
        sku=sku,
        name=f"Product {sku}",
        category="Dairy",
        unit_price=unit_price,
        tax_rate=tax_rate,
        status=ProductStatus.ACTIVE,
    )
    test_db.add_all([location, product])
    await test_db.flush()

    test_db.add(
        ProductBarcode(
            product_id=product.id,
            barcode=barcode,
            is_primary=True,
        )
    )
    product.barcode = barcode
    test_db.add(
        InventoryItem(
            product_id=product.id,
            location_id=location.id,
            physical_stock=qty,
            buffer=0,
        )
    )
    await test_db.commit()
    return location, product


@pytest.mark.asyncio
async def test_start_checkout_reserves_and_totals(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-1",
            barcode="11111111",
            qty=10,
            unit_price=Decimal("3.50"),
            tax_rate=Decimal("0.10"),
        )

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-1234",
            "lines": [{"barcode": "11111111", "qty": 2}],
        }
        response = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "reserved"
        assert data["sale_id"]
        assert data["lines"][0]["sku"] == product.sku
        assert Decimal(str(data["totals"]["subtotal"])) == Decimal("7.00")
        assert Decimal(str(data["totals"]["tax"])) == Decimal("0.70")
        assert Decimal(str(data["totals"]["total"])) == Decimal("7.70")

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.physical_stock == 10
        assert item.buffer == 2
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_checkout_auto_creates_inventory_item(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location = Location(
            code="FLOOR-02",
            name="Floor 02",
            location_type=LocationType.FLOOR,
        )
        product = Product(
            sku="POS-CHK-AUTO-1",
            name="Auto Create Item",
            category="Dairy",
            unit_price=Decimal("4.25"),
            tax_rate=Decimal("0.12"),
            status=ProductStatus.ACTIVE,
        )
        test_db.add_all([location, product])
        await test_db.flush()

        barcode_value = "44444444"
        test_db.add(
            ProductBarcode(
                product_id=product.id,
                barcode=barcode_value,
                is_primary=True,
            )
        )
        product.barcode = barcode_value
        await test_db.commit()

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-auto-1111",
            "lines": [{"barcode": barcode_value, "qty": 3}],
            "auto_create_inventory": True,
        }
        response = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item is not None
        assert item.physical_stock == 3
        assert item.buffer == 3
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_checkout_idempotent(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-2",
            barcode="22222222",
            qty=5,
            unit_price=Decimal("2.00"),
            tax_rate=Decimal("0.05"),
        )

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-5678",
            "lines": [{"barcode": "22222222", "qty": 1}],
        }
        first = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        second = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.json()["sale_id"] == second.json()["sale_id"]

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.buffer == 1

        sale_count = await test_db.scalar(select(func.count()).select_from(PosSale))
        assert sale_count == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_commit_checkout_idempotent(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-3",
            barcode="33333333",
            qty=3,
            unit_price=Decimal("1.25"),
            tax_rate=Decimal("0.08"),
        )

        start_payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-9012",
            "lines": [{"barcode": "33333333", "qty": 2}],
        }
        start = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=start_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        sale_id = start.json()["sale_id"]

        commit_payload = {
            "sale_id": sale_id,
            "idempotency_key": "checkout-9012",
        }
        first = await async_client.post(
            "/api/v1/pos/checkout/commit",
            json=commit_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        second = await async_client.post(
            "/api/v1/pos/checkout/commit",
            json=commit_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert first.status_code == status.HTTP_200_OK
        assert second.status_code == status.HTTP_200_OK
        assert first.json()["sale_id"] == sale_id
        assert second.json()["status"] == "committed"

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.physical_stock == 1
        assert item.buffer == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cancel_checkout_releases_buffer(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-4",
            barcode="44444444",
            qty=6,
            unit_price=Decimal("2.20"),
            tax_rate=Decimal("0.05"),
        )

        start_payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-3456",
            "lines": [{"barcode": "44444444", "qty": 3}],
        }
        start = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=start_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        sale_id = start.json()["sale_id"]

        cancel = await async_client.post(
            "/api/v1/pos/checkout/cancel",
            json={"sale_id": sale_id},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert cancel.status_code == status.HTTP_200_OK
        assert cancel.json()["status"] == "cancelled"

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.buffer == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_start_checkout_insufficient_stock(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, _product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-5",
            barcode="55555555",
            qty=1,
            unit_price=Decimal("3.00"),
            tax_rate=Decimal("0.10"),
        )

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-7890",
            "lines": [{"barcode": "55555555", "qty": 2}],
        }
        response = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_commit_checkout_expired_reservation(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-6",
            barcode="66666666",
            qty=4,
            unit_price=Decimal("1.00"),
            tax_rate=Decimal("0.05"),
        )

        start_payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-1122",
            "lines": [{"barcode": "66666666", "qty": 2}],
        }
        start = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=start_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        sale_id = start.json()["sale_id"]

        sale = await test_db.scalar(select(PosSale).where(PosSale.id == sale_id))
        sale.reserved_until = datetime.now(UTC) - timedelta(minutes=1)
        await test_db.commit()

        commit_payload = {
            "sale_id": sale_id,
            "idempotency_key": "checkout-1122",
        }
        response = await async_client.post(
            "/api/v1/pos/checkout/commit",
            json=commit_payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_409_CONFLICT

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.physical_stock == 4
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_expire_reserved_sales_releases_buffer(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-7",
            barcode="77777777",
            qty=8,
            unit_price=Decimal("4.00"),
            tax_rate=Decimal("0.10"),
        )

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-3344",
            "lines": [{"barcode": "77777777", "qty": 3}],
        }
        start = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        sale_id = start.json()["sale_id"]

        sale = await test_db.scalar(select(PosSale).where(PosSale.id == sale_id))
        sale.reserved_until = datetime.now(UTC) - timedelta(minutes=5)
        await test_db.commit()

        result = await pos_service.expire_reserved_sales(test_db, datetime.now(UTC))
        assert result["expired"] == 1

        expired_sale = await test_db.scalar(select(PosSale).where(PosSale.id == sale_id))
        assert expired_sale.status == PosSaleStatus.EXPIRED

        item = await test_db.scalar(
            select(InventoryItem).where(
                InventoryItem.product_id == product.id,
                InventoryItem.location_id == location.id,
            )
        )
        assert item.buffer == 0
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_checkout_recovery_endpoints(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location, _product = await seed_pos_inventory(
            test_db,
            sku="POS-CHK-8",
            barcode="88888888",
            qty=5,
            unit_price=Decimal("2.50"),
            tax_rate=Decimal("0.10"),
        )

        payload = {
            "location_id": location.id,
            "idempotency_key": "checkout-5566",
            "lines": [{"barcode": "88888888", "qty": 2}],
        }
        start = await async_client.post(
            "/api/v1/pos/checkout/start",
            json=payload,
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        sale_id = start.json()["sale_id"]

        by_id = await async_client.get(
            f"/api/v1/pos/checkout/{sale_id}",
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        by_key = await async_client.get(
            f"/api/v1/pos/checkout/by-key/{payload['idempotency_key']}",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert by_id.status_code == status.HTTP_200_OK
        assert by_key.status_code == status.HTTP_200_OK
        assert by_id.json()["sale_id"] == sale_id
        assert by_key.json()["sale_id"] == sale_id
        assert by_id.json()["status"] == "reserved"
        assert by_id.json()["totals"] == start.json()["totals"]
    finally:
        app.dependency_overrides.clear()
