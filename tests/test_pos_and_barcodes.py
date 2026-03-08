"""
POS and Barcode Tests
---------------------
Tests for POS lookup and barcode uniqueness.
"""

from decimal import Decimal

import pytest
from fastapi import status

from src.api.deps import get_db
from src.core.exceptions import ValidationError
from src.main import app
from src.modules.inventory.models import InventoryItem, Location, LocationType
from src.modules.pos.schemas import PosLookupResponse
from src.modules.products.models import Product, ProductBarcode, ProductStatus
from src.modules.products.service import CreateProductInput, product_service
from scripts.import_products_from_mapping import import_products_from_mapping


@pytest.mark.asyncio
async def test_pos_lookup_success(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location = Location(
            code="FLOOR-01",
            name="Floor 01",
            location_type=LocationType.FLOOR,
        )
        product = Product(
            sku="MILK-2L",
            name="Whole Milk 2L",
            category="Dairy",
            unit_price=Decimal("3.50"),
            tax_rate=Decimal("0.10"),
            status=ProductStatus.ACTIVE,
        )
        test_db.add_all([location, product])
        await test_db.flush()

        barcode_value = "0123456789012"
        test_db.add(
            ProductBarcode(
                product_id=product.id,
                barcode=barcode_value,
                is_primary=True,
            )
        )
        product.barcode = barcode_value
        test_db.add(
            InventoryItem(
                product_id=product.id,
                location_id=location.id,
                physical_stock=10,
                buffer=2,
            )
        )
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/pos/lookup",
            params={"barcode": barcode_value},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        PosLookupResponse.model_validate(data)
        assert data["sku"] == "MILK-2L"
        assert data["name"] == "Whole Milk 2L"
        assert data["status"] == "active"
        assert data["primary_barcode"] == barcode_value
        assert data["barcodes"] == [barcode_value]
        assert Decimal(str(data["unit_price"])) == Decimal("3.50")
        assert Decimal(str(data["tax_rate"])) == Decimal("0.10")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pos_lookup_unknown_barcode(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        response = await async_client.get(
            "/api/v1/pos/lookup",
            params={"barcode": "00000000"},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_barcode_uniqueness_enforced(test_db):
    await product_service.create_product(
        test_db,
        CreateProductInput(
            sku="SKU-ONE",
            name="First Product",
            unit_price=Decimal("5.00"),
            barcode="12345678",
        ),
    )

    with pytest.raises(ValidationError):
        await product_service.create_product(
            test_db,
            CreateProductInput(
                sku="SKU-TWO",
                name="Second Product",
                unit_price=Decimal("6.00"),
                barcode="12345678",
            ),
        )


@pytest.mark.asyncio
async def test_importer_idempotency(tmp_path, test_db):
    csv_path = tmp_path / "products.csv"
    csv_path.write_text(
        "Barcode,Product Name,Price,SKU\n"
        "11111111,Import Product,2.50,IMP-001\n"
    )

    first = await import_products_from_mapping(test_db, str(csv_path))
    second = await import_products_from_mapping(test_db, str(csv_path))

    assert first["created"] == 1
    assert first["barcodes_added"] == 1
    assert second["created"] == 0
    assert second["updated"] == 0
    assert second["barcodes_added"] == 0
    assert second["products_total"] == first["products_total"]
    assert second["barcodes_total"] == first["barcodes_total"]
