"""
Inventory Location Tests
------------------------
Verify location listing for POS lookup.
"""

import pytest
from fastapi import status

from src.api.deps import get_db
from src.main import app
from src.modules.inventory.models import Location, LocationType


@pytest.mark.asyncio
async def test_list_locations_returns_ids(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location_one = Location(
            code="LIDCOMBE",
            name="Lidcombe Floor",
            location_type=LocationType.FLOOR,
        )
        location_two = Location(
            code="BACKROOM-01",
            name="Backroom",
            location_type=LocationType.BACKROOM,
        )
        test_db.add_all([location_one, location_two])
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/inventory/locations",
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        codes = {item["code"] for item in data}
        ids = {item["id"] for item in data}
        assert "LIDCOMBE" in codes
        assert "BACKROOM-01" in codes
        assert len(ids) == len(data)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_locations_filter_by_code(async_client, test_db, staff_token):
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        location = Location(
            code="LIDCOMBE",
            name="Lidcombe Floor",
            location_type=LocationType.FLOOR,
        )
        test_db.add(location)
        await test_db.commit()

        response = await async_client.get(
            "/api/v1/inventory/locations",
            params={"code": "lidcombe"},
            headers={"Authorization": f"Bearer {staff_token}"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["code"] == "LIDCOMBE"
        assert data[0]["id"] == location.id
    finally:
        app.dependency_overrides.clear()
