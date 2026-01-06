"""
Inventory Model Tests
---------------------
Unit tests for inventory domain models.

These tests verify:
1. Derived fields compute correctly
2. Business rule enforcement
3. Constraint validation
4. Concurrency safety patterns
"""

import pytest
from decimal import Decimal
from datetime import datetime, timedelta, UTC

from src.modules.inventory.models import (
    InventoryItem,
    InventoryBatch,
    Location,
    LocationType,
    StockMovement,
    MovementType,
    MovementReason,
)
from src.modules.products.models import Product, ProductCategory


class TestInventoryItem:
    """Tests for InventoryItem model."""
    
    def test_online_available_basic(self):
        """online_available = max(physical_stock - buffer, 0)"""
        item = InventoryItem(
            physical_stock=100,
            buffer=20,
        )
        assert item.online_available == 80
    
    def test_online_available_zero_buffer(self):
        """With no buffer, all stock is available."""
        item = InventoryItem(
            physical_stock=50,
            buffer=0,
        )
        assert item.online_available == 50
    
    def test_online_available_buffer_exceeds_stock(self):
        """When buffer >= physical_stock, online_available = 0."""
        item = InventoryItem(
            physical_stock=10,
            buffer=15,  # More than physical stock
        )
        assert item.online_available == 0  # Never negative
    
    def test_online_available_zero_stock(self):
        """Zero stock means zero available."""
        item = InventoryItem(
            physical_stock=0,
            buffer=0,
        )
        assert item.online_available == 0
    
    def test_is_low_stock(self):
        """Low stock flag based on reorder point."""
        item = InventoryItem(
            physical_stock=5,
            reorder_point=10,
        )
        assert item.is_low_stock is True
        
        item.physical_stock = 15
        assert item.is_low_stock is False
    
    def test_is_out_of_stock(self):
        """Out of stock when physical_stock = 0."""
        item = InventoryItem(physical_stock=0)
        assert item.is_out_of_stock is True
        
        item.physical_stock = 1
        assert item.is_out_of_stock is False
    
    def test_can_fulfill(self):
        """Can fulfill based on online_available."""
        item = InventoryItem(
            physical_stock=100,
            buffer=30,
        )
        # online_available = 70
        assert item.can_fulfill(50) is True
        assert item.can_fulfill(70) is True
        assert item.can_fulfill(71) is False
        assert item.can_fulfill(100) is False  # Buffer reserved
    
    def test_adjust_stock_increase(self):
        """Increasing stock works and increments version."""
        item = InventoryItem(
            physical_stock=50,
            version=1,
        )
        item.adjust_stock(+25)
        
        assert item.physical_stock == 75
        assert item.version == 2
    
    def test_adjust_stock_decrease(self):
        """Decreasing stock works within limits."""
        item = InventoryItem(
            physical_stock=50,
            version=1,
        )
        item.adjust_stock(-20)
        
        assert item.physical_stock == 30
        assert item.version == 2
    
    def test_adjust_stock_negative_rejected(self):
        """Cannot reduce stock below zero."""
        item = InventoryItem(physical_stock=10)
        
        with pytest.raises(ValueError, match="Cannot reduce stock below 0"):
            item.adjust_stock(-15)
        
        # Stock unchanged
        assert item.physical_stock == 10
    
    def test_adjust_buffer_increase(self):
        """Increasing buffer works."""
        item = InventoryItem(buffer=10, version=1)
        item.adjust_buffer(+5)
        
        assert item.buffer == 15
        assert item.version == 2
    
    def test_adjust_buffer_negative_rejected(self):
        """Cannot reduce buffer below zero."""
        item = InventoryItem(buffer=5)
        
        with pytest.raises(ValueError, match="Cannot reduce buffer below 0"):
            item.adjust_buffer(-10)
        
        assert item.buffer == 5


class TestInventoryBatch:
    """Tests for InventoryBatch (expiry tracking)."""
    
    def test_is_expired_future_date(self):
        """Not expired if expiry is in the future."""
        batch = InventoryBatch(
            quantity=10,
            expiry_date=datetime.now(UTC) + timedelta(days=7),
        )
        assert batch.is_expired is False
    
    def test_is_expired_past_date(self):
        """Expired if expiry is in the past."""
        batch = InventoryBatch(
            quantity=10,
            expiry_date=datetime.now(UTC) - timedelta(days=1),
        )
        assert batch.is_expired is True
    
    def test_is_expired_no_expiry(self):
        """Non-perishables (no expiry) are never expired."""
        batch = InventoryBatch(
            quantity=10,
            expiry_date=None,
        )
        assert batch.is_expired is False
    
    def test_days_until_expiry(self):
        """Days until expiry calculation."""
        batch = InventoryBatch(
            quantity=10,
            expiry_date=datetime.now(UTC) + timedelta(days=5),
        )
        # Allow for timing variance
        assert batch.days_until_expiry in [4, 5]
    
    def test_days_until_expiry_none(self):
        """No expiry date means None for days."""
        batch = InventoryBatch(
            quantity=10,
            expiry_date=None,
        )
        assert batch.days_until_expiry is None


class TestStockMovement:
    """Tests for StockMovement audit records."""
    
    def test_is_increase(self):
        """Positive delta is an increase."""
        movement = StockMovement(
            quantity_delta=10,
            quantity_before=50,
            quantity_after=60,
            movement_type=MovementType.RECEIVING,
            user_id="user-1",
            inventory_item_id="item-1",
        )
        assert movement.is_increase is True
        assert movement.is_decrease is False
    
    def test_is_decrease(self):
        """Negative delta is a decrease."""
        movement = StockMovement(
            quantity_delta=-5,
            quantity_before=50,
            quantity_after=45,
            movement_type=MovementType.SALE,
            user_id="user-1",
            inventory_item_id="item-1",
        )
        assert movement.is_increase is False
        assert movement.is_decrease is True
    
    def test_movement_consistency(self):
        """Verify before + delta = after."""
        movement = StockMovement(
            quantity_delta=-10,
            quantity_before=100,
            quantity_after=90,
            movement_type=MovementType.SALE,
            user_id="user-1",
            inventory_item_id="item-1",
        )
        assert movement.quantity_before + movement.quantity_delta == movement.quantity_after


class TestProduct:
    """Tests for Product model."""
    
    def test_margin_calculation(self):
        """Margin = (price - cost) / cost * 100."""
        product = Product(
            sku="TEST-001",
            name="Test Product",
            unit_price=Decimal("10.00"),
            cost_price=Decimal("8.00"),
        )
        # (10 - 8) / 8 * 100 = 25%
        assert product.margin == Decimal("25")
    
    def test_margin_no_cost(self):
        """Margin is None when cost is not set."""
        product = Product(
            sku="TEST-001",
            name="Test Product",
            unit_price=Decimal("10.00"),
            cost_price=None,
        )
        assert product.margin is None
    
    def test_price_with_tax(self):
        """Price with tax calculation."""
        product = Product(
            sku="TEST-001",
            name="Test Product",
            unit_price=Decimal("100.00"),
            tax_rate=Decimal("0.13"),  # 13% tax
        )
        # 100 * 1.13 = 113
        assert product.price_with_tax == Decimal("113.00")


class TestOptimisticLocking:
    """Tests for optimistic locking behavior."""
    
    def test_version_increments_on_stock_change(self):
        """Version increases with each stock adjustment."""
        item = InventoryItem(physical_stock=100, version=1)
        
        item.adjust_stock(+10)
        assert item.version == 2
        
        item.adjust_stock(-5)
        assert item.version == 3
        
        item.adjust_buffer(+5)
        assert item.version == 4
    
    def test_concurrent_modification_scenario(self):
        """
        Simulates how optimistic locking prevents lost updates.
        
        In real usage:
        1. Staff A reads item (version=1)
        2. Staff B reads item (version=1)
        3. Staff B saves (version becomes 2)
        4. Staff A tries to save with version=1 → DB rejects (0 rows affected)
        """
        # Both "users" start with same version
        user_a_version = 1
        user_b_version = 1
        
        # Simulate the in-memory items
        item = InventoryItem(physical_stock=100, version=1)
        
        # User B saves first
        item.adjust_stock(+10)  # version becomes 2
        current_version = item.version
        
        # User A's version is now stale
        assert user_a_version < current_version
        
        # In the service layer, we would check:
        # UPDATE ... WHERE id = ? AND version = ?
        # If version mismatch, 0 rows affected → raise ConcurrencyError

