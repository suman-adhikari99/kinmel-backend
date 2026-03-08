"""
Product Barcode Response Tests
------------------------------
Verify barcode fields are exposed consistently in product responses.
"""

import pytest
from fastapi import status

from src.api.deps import get_db
from src.main import app


@pytest.mark.asyncio
async def test_create_product_with_barcodes_returns_primary_and_list(
    async_client,
    test_db,
    manager_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "sku": "TEST-BC-001",
            "name": "Barcode Product",
            "unit_price": 3.50,
            "barcodes": ["11111111", "22222222"],
            "primary_barcode": "22222222",
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["barcode"] == "22222222"
        assert data["primary_barcode"] == "22222222"
        assert data["barcodes"] == ["22222222", "11111111"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_create_product_with_deprecated_barcode_returns_fields(
    async_client,
    test_db,
    manager_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "sku": "TEST-BC-LEGACY",
            "name": "Legacy Barcode Product",
            "unit_price": 2.25,
            "barcode": "12345678",
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["barcode"] == "12345678"
        assert data["primary_barcode"] == "12345678"
        assert data["barcodes"] == ["12345678"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_barcode_uniqueness_enforced_via_api(
    async_client,
    test_db,
    manager_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "sku": "TEST-BC-UNIQ-1",
            "name": "Unique Barcode Product 1",
            "unit_price": 4.99,
            "barcode": "87654321",
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED

        payload = {
            "sku": "TEST-BC-UNIQ-2",
            "name": "Unique Barcode Product 2",
            "unit_price": 5.25,
            "barcode": "87654321",
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["detail"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_barcode_reassigned_on_update(
    async_client,
    test_db,
    manager_token,
):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        payload = {
            "sku": "TEST-BC-MOVE-1",
            "name": "Barcode Source Product",
            "unit_price": 3.75,
            "barcode": "9300682047944",
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED

        payload = {
            "sku": "TEST-BC-MOVE-2",
            "name": "Barcode Target Product",
            "unit_price": 4.25,
        }
        response = await async_client.post(
            "/api/v1/products",
            json=payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED

        update_payload = {
            "barcodes": ["9300682047944"],
            "primary_barcode": "9300682047944",
        }
        update = await async_client.put(
            "/api/v1/products/TEST-BC-MOVE-2",
            json=update_payload,
            headers={"Authorization": f"Bearer {manager_token}"},
        )
        assert update.status_code == status.HTTP_200_OK
        data = update.json()
        assert data["barcode"] == "9300682047944"
        assert data["primary_barcode"] == "9300682047944"
        assert data["barcodes"] == ["9300682047944"]

        source = await async_client.get("/api/v1/products/TEST-BC-MOVE-1")
        assert source.status_code == status.HTTP_200_OK
        source_data = source.json()
        assert source_data["barcode"] is None
        assert source_data["barcodes"] == []
    finally:
        app.dependency_overrides.clear()
