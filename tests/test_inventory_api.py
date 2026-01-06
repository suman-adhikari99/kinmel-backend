"""
Inventory API Tests
-------------------
Tests for REST endpoints and role-based access control.

These tests verify:
1. Endpoints call correct service methods
2. Role restrictions are enforced
3. Error responses are structured correctly
4. Request validation works
"""

import pytest
from datetime import datetime, timedelta, UTC
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import status
from fastapi.testclient import TestClient

from src.core.security import Role, create_access_token
from src.main import app
from src.modules.inventory.models import MovementReason, MovementType


# ═══════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def client():
    """Test client."""
    return TestClient(app)


@pytest.fixture
def staff_headers():
    """Headers with staff-level JWT."""
    token = create_access_token(user_id="staff-001", role=Role.STAFF)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def manager_headers():
    """Headers with manager-level JWT."""
    token = create_access_token(user_id="manager-001", role=Role.MANAGER)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers():
    """Headers with admin/owner-level JWT."""
    token = create_access_token(user_id="owner-001", role=Role.ADMIN)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_service_result():
    """Mock successful service operation result."""
    mock_item = MagicMock()
    mock_item.id = "item-123"
    mock_item.product_id = "prod-123"
    mock_item.location_id = "loc-123"
    mock_item.physical_stock = 100
    mock_item.buffer = 10
    mock_item.reorder_point = 20
    mock_item.max_stock = None
    mock_item.version = 2
    mock_item.is_active = True
    mock_item.created_at = datetime.now(UTC)
    mock_item.updated_at = datetime.now(UTC)
    mock_item.product = None
    mock_item.location = None
    
    mock_movement = MagicMock()
    mock_movement.id = "mov-123"
    mock_movement.inventory_item_id = "item-123"
    mock_movement.movement_type = MovementType.RECEIVING
    mock_movement.reason = MovementReason.SUPPLIER_DELIVERY
    mock_movement.quantity_delta = 50
    mock_movement.quantity_before = 50
    mock_movement.quantity_after = 100
    mock_movement.user_id = "user-123"
    mock_movement.reference_id = "PO-001"
    mock_movement.reference_type = "purchase_order"
    mock_movement.notes = None
    mock_movement.created_at = datetime.now(UTC)
    
    result = MagicMock()
    result.inventory_item = mock_item
    result.movement = mock_movement
    result.previous_stock = 50
    result.new_stock = 100
    
    return result


# ═══════════════════════════════════════════════════════════════════════════
# AUTHENTICATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthentication:
    """Test authentication requirements."""
    
    def test_unauthenticated_request_rejected(self, client):
        """Requests without token are rejected."""
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 10,
            },
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_invalid_token_rejected(self, client):
        """Requests with invalid token are rejected."""
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 10,
            },
            headers={"Authorization": "Bearer invalid-token"},
        )
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ═══════════════════════════════════════════════════════════════════════════
# ROLE-BASED ACCESS CONTROL TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRoleBasedAccess:
    """Test role restrictions on endpoints."""
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_staff_can_receive_stock(
        self, mock_service, client, staff_headers, mock_service_result
    ):
        """Staff can receive stock."""
        mock_service.receive_stock = AsyncMock(return_value=mock_service_result)
        
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 50,
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["success"] is True
    
    def test_staff_cannot_adjust_stock(self, client, staff_headers):
        """Staff are denied stock adjustments."""
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "cycle_count",
                "notes": "Regular cycle count adjustment",
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        
        data = response.json()
        assert data["detail"]["code"] == "INSUFFICIENT_ROLE"
        assert data["detail"]["required_role"] == "MANAGER"
        assert data["detail"]["your_role"] == "staff"
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_manager_can_adjust_stock(
        self, mock_service, client, manager_headers, mock_service_result
    ):
        """Managers can adjust stock."""
        mock_service.adjust_stock = AsyncMock(return_value=mock_service_result)
        
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "cycle_count",
                "notes": "Regular cycle count adjustment",
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    def test_staff_cannot_dispose_stock(self, client, staff_headers):
        """Staff cannot dispose stock."""
        response = client.post(
            "/api/v1/inventory/dispose",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 5,
                "reason": "expired",
                "notes": "Product past expiration date",
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_manager_can_dispose_stock(
        self, mock_service, client, manager_headers, mock_service_result
    ):
        """Managers can dispose stock."""
        mock_service.dispose_stock = AsyncMock(return_value=mock_service_result)
        
        response = client.post(
            "/api/v1/inventory/dispose",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 5,
                "reason": "expired",
                "notes": "Product past expiration date",
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_staff_can_fulfill_order(
        self, mock_service, client, staff_headers, mock_service_result
    ):
        """Staff (cashiers) can fulfill orders."""
        mock_service.fulfill_order = AsyncMock(return_value=mock_service_result)
        
        response = client.post(
            "/api/v1/inventory/fulfill",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 2,
                "order_id": "ORD-12345",
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestRequestValidation:
    """Test Pydantic request validation."""
    
    def test_receive_negative_quantity_rejected(self, client, staff_headers):
        """Negative quantity is rejected."""
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": -10,
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_receive_zero_quantity_rejected(self, client, staff_headers):
        """Zero quantity is rejected."""
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 0,
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_receive_excessive_quantity_rejected(self, client, staff_headers):
        """Quantity over limit is rejected."""
        response = client.post(
            "/api/v1/inventory/receive",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 100000,  # Over 10000 limit
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_adjust_requires_notes(self, client, manager_headers):
        """Adjustment requires notes explanation."""
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "cycle_count",
                # Missing notes
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_adjust_notes_too_short_rejected(self, client, manager_headers):
        """Adjustment notes must be at least 10 chars."""
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "cycle_count",
                "notes": "short",  # Too short
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_invalid_adjustment_reason_rejected(self, client, manager_headers):
        """Invalid adjustment reason is rejected."""
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "customer_sale",  # Not valid for adjustment
                "notes": "This should fail validation",
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_sku_normalized_to_uppercase(self, client, staff_headers):
        """SKU is normalized to uppercase."""
        with patch("src.modules.inventory.router.inventory_service") as mock_service:
            mock_result = MagicMock()
            mock_result.inventory_item = MagicMock(
                id="x", product_id="x", location_id="x",
                physical_stock=100, buffer=0, reorder_point=10,
                max_stock=None, version=1, is_active=True,
                created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
                product=None, location=None,
            )
            mock_result.movement = MagicMock(
                id="x", inventory_item_id="x",
                movement_type=MovementType.RECEIVING,
                reason=MovementReason.SUPPLIER_DELIVERY,
                quantity_delta=10, quantity_before=90, quantity_after=100,
                user_id="x", reference_id=None, reference_type=None,
                notes=None, created_at=datetime.now(UTC),
            )
            mock_result.previous_stock = 90
            mock_result.new_stock = 100
            
            mock_service.receive_stock = AsyncMock(return_value=mock_result)
            
            response = client.post(
                "/api/v1/inventory/receive",
                json={
                    "sku": "milk-2l",  # Lowercase
                    "location_id": "loc-1",
                    "quantity": 10,
                },
                headers=staff_headers,
            )
            
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify service was called with uppercase SKU
            call_args = mock_service.receive_stock.call_args
            assert call_args[0][1].sku == "MILK-2L"


# ═══════════════════════════════════════════════════════════════════════════
# ERROR RESPONSE TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorResponses:
    """Test error response formatting."""
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_not_found_error_format(self, mock_service, client, staff_headers):
        """NotFoundError returns 404 with structured response."""
        from src.core.exceptions import NotFoundError
        
        mock_service.get_stock_level = AsyncMock(
            side_effect=NotFoundError("InventoryItem", "UNKNOWN-SKU@loc-1")
        )
        
        response = client.get(
            "/api/v1/inventory/stock/UNKNOWN-SKU",
            params={"location_id": "loc-1"},
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert data["detail"]["code"] == "NOT_FOUND"
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_insufficient_stock_error_format(
        self, mock_service, client, staff_headers
    ):
        """InsufficientStockError returns 422 with details."""
        from src.core.exceptions import InsufficientStockError
        
        mock_service.reserve_stock = AsyncMock(
            side_effect=InsufficientStockError(
                sku="MILK-2L",
                requested=100,
                available=5,
            )
        )
        
        response = client.post(
            "/api/v1/inventory/reserve",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "quantity": 100,
                "order_id": "ORD-123",
            },
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        assert data["detail"]["code"] == "INSUFFICIENT_STOCK"
        assert data["detail"]["requested"] == 100
        assert data["detail"]["available"] == 5
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_concurrency_error_format(
        self, mock_service, client, manager_headers
    ):
        """ConcurrencyError returns 409 with retry hint."""
        from src.core.exceptions import ConcurrencyError
        
        mock_service.adjust_stock = AsyncMock(
            side_effect=ConcurrencyError("InventoryItem", "item-123")
        )
        
        response = client.post(
            "/api/v1/inventory/adjust",
            json={
                "sku": "MILK-2L",
                "location_id": "loc-1",
                "new_quantity": 100,
                "reason": "cycle_count",
                "notes": "Regular count adjustment",
            },
            headers=manager_headers,
        )
        
        assert response.status_code == status.HTTP_409_CONFLICT
        data = response.json()
        assert data["detail"]["code"] == "CONCURRENT_MODIFICATION"
        assert "refresh" in data["detail"]["action"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# QUERY ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════════════════════

class TestQueryEndpoints:
    """Test read-only query endpoints."""
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_get_stock_level(self, mock_service, client, staff_headers):
        """Get stock level for a SKU."""
        mock_service.get_stock_level = AsyncMock(return_value={
            "sku": "MILK-2L",
            "location_id": "loc-1",
            "physical_stock": 100,
            "buffer": 10,
            "online_available": 90,
            "is_low_stock": False,
            "reorder_point": 20,
        })
        
        response = client.get(
            "/api/v1/inventory/stock/MILK-2L",
            params={"location_id": "loc-1"},
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["physical_stock"] == 100
        assert data["online_available"] == 90
    
    @patch("src.modules.inventory.router.inventory_service")
    def test_get_low_stock_alerts(self, mock_service, client, staff_headers):
        """Get low stock alerts."""
        mock_item = MagicMock()
        mock_item.id = "item-1"
        mock_item.product = MagicMock(sku="MILK-2L", name="Milk 2L")
        mock_item.location = MagicMock(code="FLOOR-A1")
        mock_item.physical_stock = 5
        mock_item.reorder_point = 20
        
        mock_service.get_low_stock_alerts = AsyncMock(return_value=[mock_item])
        
        response = client.get(
            "/api/v1/inventory/alerts/low-stock",
            headers=staff_headers,
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 1
        assert data[0]["sku"] == "MILK-2L"
        assert data[0]["shortage"] == 15  # 20 - 5

