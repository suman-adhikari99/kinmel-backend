"""
Inventory Service Tests
-----------------------
Integration tests for inventory service business logic.

These tests verify:
1. Stock operations work correctly
2. Audit trails are created
3. Business rules are enforced
4. Concurrency is handled safely
"""

import pytest
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.exceptions import (
    ConcurrencyError,
    InsufficientStockError,
    NotFoundError,
    StockAdjustmentTooLargeError,
    ValidationError,
)
from src.modules.inventory.models import (
    InventoryItem,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.inventory.service import (
    AdjustmentInput,
    InventoryService,
    ReceivingInput,
    ReservationInput,
    StockOperationResult,
)


class TestReceiveStock:
    """Tests for stock receiving operations."""
    
    @pytest.mark.asyncio
    async def test_receive_stock_success(self):
        """Successfully receive stock into existing inventory."""
        # Setup mock repository
        mock_repo = AsyncMock()
        
        # Mock existing inventory item
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 50
        mock_item.buffer = 10
        mock_item.version = 1
        mock_item.online_available = 40
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        
        mock_movement = MagicMock(spec=StockMovement)
        mock_movement.id = "mov-123"
        mock_repo.create_movement.return_value = mock_movement
        
        service = InventoryService(repository=mock_repo)
        
        # Execute
        input_data = ReceivingInput(
            sku="MILK-2L",
            location_id="loc-floor-1",
            quantity=25,
            user_id="user-123",
            reference_id="PO-001",
            notes="Regular delivery",
        )
        
        mock_session = AsyncMock()
        result = await service.receive_stock(mock_session, input_data)
        
        # Verify
        assert result.previous_stock == 50
        assert result.new_stock == 75
        assert result.delta == 25
        
        # Verify optimistic lock was used
        mock_repo.update_stock_optimistic.assert_called_once_with(
            mock_session,
            "item-123",
            new_physical_stock=75,
            expected_version=1,
        )
        
        # Verify audit record created
        mock_repo.create_movement.assert_called_once()
        call_kwargs = mock_repo.create_movement.call_args.kwargs
        assert call_kwargs["movement_type"] == MovementType.RECEIVING
        assert call_kwargs["quantity_delta"] == 25
        assert call_kwargs["quantity_before"] == 50
        assert call_kwargs["quantity_after"] == 75
    
    @pytest.mark.asyncio
    async def test_receive_stock_negative_quantity_rejected(self):
        """Receiving negative quantity should fail."""
        service = InventoryService()
        
        input_data = ReceivingInput(
            sku="MILK-2L",
            location_id="loc-1",
            quantity=-10,  # Invalid
            user_id="user-123",
        )
        
        mock_session = AsyncMock()
        
        with pytest.raises(ValidationError) as exc_info:
            await service.receive_stock(mock_session, input_data)
        
        assert "positive" in str(exc_info.value.message).lower()
    
    @pytest.mark.asyncio
    async def test_receive_stock_with_expiry_creates_batch(self):
        """Receiving perishables should create a batch."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 0
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        mock_repo.create_batch.return_value = MagicMock(id="batch-123")
        
        service = InventoryService(repository=mock_repo)
        
        expiry = datetime.now(UTC) + timedelta(days=14)
        input_data = ReceivingInput(
            sku="YOGURT-500ML",
            location_id="loc-cold-1",
            quantity=50,
            user_id="user-123",
            expiry_date=expiry,
            batch_number="LOT-2024-001",
        )
        
        mock_session = AsyncMock()
        await service.receive_stock(mock_session, input_data)
        
        # Verify batch was created
        mock_repo.create_batch.assert_called_once()
        call_kwargs = mock_repo.create_batch.call_args.kwargs
        assert call_kwargs["quantity"] == 50
        assert call_kwargs["batch_number"] == "LOT-2024-001"
        assert call_kwargs["expiry_date"] == expiry


class TestAdjustStock:
    """Tests for stock adjustment operations."""
    
    @pytest.mark.asyncio
    async def test_adjust_stock_increase(self):
        """Adjusting stock upward works."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 50
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        
        input_data = AdjustmentInput(
            sku="BREAD-WHITE",
            location_id="loc-1",
            new_quantity=55,  # +5 from 50
            user_id="user-123",
            reason=MovementReason.CYCLE_COUNT,
            notes="Found extra stock behind display",
        )
        
        mock_session = AsyncMock()
        result = await service.adjust_stock(mock_session, input_data)
        
        assert result.previous_stock == 50
        assert result.new_stock == 55
        assert result.delta == 5
    
    @pytest.mark.asyncio
    async def test_adjust_stock_decrease(self):
        """Adjusting stock downward works."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        
        input_data = AdjustmentInput(
            sku="CHIPS-LARGE",
            location_id="loc-1",
            new_quantity=95,  # -5 from 100
            user_id="user-123",
            reason=MovementReason.SHRINKAGE,
            notes="Weekly shrinkage adjustment",
        )
        
        mock_session = AsyncMock()
        result = await service.adjust_stock(mock_session, input_data)
        
        assert result.delta == -5
    
    @pytest.mark.asyncio
    async def test_large_adjustment_blocked(self):
        """Large adjustments are blocked by safety check."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        
        service = InventoryService(repository=mock_repo)
        
        # Try to adjust by more than 50% (default threshold)
        input_data = AdjustmentInput(
            sku="PRODUCT-X",
            location_id="loc-1",
            new_quantity=10,  # -90 from 100, which is 90%!
            user_id="user-123",
            reason=MovementReason.CYCLE_COUNT,
        )
        
        mock_session = AsyncMock()
        
        with pytest.raises(StockAdjustmentTooLargeError):
            await service.adjust_stock(mock_session, input_data)
    
    @pytest.mark.asyncio
    async def test_large_adjustment_allowed_with_override(self):
        """Managers can bypass large adjustment check."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        
        input_data = AdjustmentInput(
            sku="PRODUCT-X",
            location_id="loc-1",
            new_quantity=10,  # -90 from 100
            user_id="manager-123",
            reason=MovementReason.AUDIT_CORRECTION,
            skip_large_adjustment_check=True,  # Manager override
        )
        
        mock_session = AsyncMock()
        result = await service.adjust_stock(mock_session, input_data)
        
        # Should succeed with override
        assert result.new_stock == 10
    
    @pytest.mark.asyncio
    async def test_negative_stock_rejected(self):
        """Cannot adjust to negative stock."""
        service = InventoryService()
        
        input_data = AdjustmentInput(
            sku="PRODUCT-X",
            location_id="loc-1",
            new_quantity=-5,  # Invalid
            user_id="user-123",
            reason=MovementReason.CYCLE_COUNT,
        )
        
        mock_session = AsyncMock()
        
        with pytest.raises(ValidationError) as exc_info:
            await service.adjust_stock(mock_session, input_data)
        
        assert "negative" in str(exc_info.value.message).lower()


class TestReserveStock:
    """Tests for stock reservation (online orders)."""
    
    @pytest.mark.asyncio
    async def test_reserve_stock_success(self):
        """Successfully reserve stock for online order."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.buffer = 20
        mock_item.online_available = 80
        mock_item.version = 1
        mock_item.can_fulfill.return_value = True
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        
        input_data = ReservationInput(
            sku="MILK-2L",
            location_id="loc-1",
            quantity=10,
            user_id="system",
            order_id="ORD-12345",
        )
        
        mock_session = AsyncMock()
        await service.reserve_stock(mock_session, input_data)
        
        # Verify buffer increased, not physical stock
        mock_repo.update_stock_optimistic.assert_called_once()
        call_kwargs = mock_repo.update_stock_optimistic.call_args.kwargs
        assert call_kwargs["new_physical_stock"] == 100  # Unchanged
        assert call_kwargs["new_buffer"] == 30  # Was 20, now 30
    
    @pytest.mark.asyncio
    async def test_reserve_insufficient_stock(self):
        """Cannot reserve more than available."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 10
        mock_item.buffer = 5
        mock_item.online_available = 5  # Only 5 available
        mock_item.can_fulfill.return_value = False
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        
        service = InventoryService(repository=mock_repo)
        
        input_data = ReservationInput(
            sku="MILK-2L",
            location_id="loc-1",
            quantity=10,  # Trying to reserve 10 when only 5 available
            user_id="system",
            order_id="ORD-12345",
        )
        
        mock_session = AsyncMock()
        
        with pytest.raises(InsufficientStockError) as exc_info:
            await service.reserve_stock(mock_session, input_data)
        
        assert exc_info.value.details["requested"] == 10
        assert exc_info.value.details["available"] == 5


class TestFulfillOrder:
    """Tests for order fulfillment."""
    
    @pytest.mark.asyncio
    async def test_fulfill_order_success(self):
        """Successfully fulfill order by decrementing stock."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.buffer = 10  # Has reservation
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        
        mock_session = AsyncMock()
        result = await service.fulfill_order(
            mock_session,
            sku="MILK-2L",
            location_id="loc-1",
            quantity=5,
            user_id="cashier-1",
            order_id="ORD-12345",
        )
        
        assert result.previous_stock == 100
        assert result.new_stock == 95
        
        # Both physical and buffer should decrease
        call_kwargs = mock_repo.update_stock_optimistic.call_args.kwargs
        assert call_kwargs["new_physical_stock"] == 95
        assert call_kwargs["new_buffer"] == 5  # Was 10, sold 5
    
    @pytest.mark.asyncio
    async def test_fulfill_insufficient_stock(self):
        """Cannot fulfill more than physical stock."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 5
        mock_item.buffer = 0
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        
        service = InventoryService(repository=mock_repo)
        
        mock_session = AsyncMock()
        
        with pytest.raises(InsufficientStockError):
            await service.fulfill_order(
                mock_session,
                sku="MILK-2L",
                location_id="loc-1",
                quantity=10,  # More than available
                user_id="cashier-1",
                order_id="ORD-12345",
            )


class TestConcurrency:
    """Tests for concurrent access handling."""
    
    @pytest.mark.asyncio
    async def test_optimistic_lock_failure(self):
        """ConcurrencyError raised when version mismatch."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.side_effect = ConcurrencyError(
            "InventoryItem", "item-123"
        )
        
        service = InventoryService(repository=mock_repo)
        
        input_data = AdjustmentInput(
            sku="PRODUCT-X",
            location_id="loc-1",
            new_quantity=90,
            user_id="user-123",
            reason=MovementReason.CYCLE_COUNT,
        )
        
        mock_session = AsyncMock()
        
        with pytest.raises(ConcurrencyError) as exc_info:
            await service.adjust_stock(mock_session, input_data)
        
        assert "item-123" in str(exc_info.value.details["identifier"])


class TestAuditTrail:
    """Tests for audit trail creation."""
    
    @pytest.mark.asyncio
    async def test_movement_created_for_every_operation(self):
        """Every stock operation creates a movement record."""
        mock_repo = AsyncMock()
        
        mock_item = MagicMock(spec=InventoryItem)
        mock_item.id = "item-123"
        mock_item.physical_stock = 100
        mock_item.buffer = 0
        mock_item.version = 1
        
        mock_repo.get_by_sku_and_location.return_value = mock_item
        mock_repo.update_stock_optimistic.return_value = True
        mock_repo.create_movement.return_value = MagicMock()
        
        service = InventoryService(repository=mock_repo)
        mock_session = AsyncMock()
        
        # Adjustment
        await service.adjust_stock(
            mock_session,
            AdjustmentInput(
                sku="X",
                location_id="L",
                new_quantity=90,
                user_id="U",
                reason=MovementReason.CYCLE_COUNT,
            ),
        )
        
        # Verify movement was created
        assert mock_repo.create_movement.called
        call_kwargs = mock_repo.create_movement.call_args.kwargs
        
        # Verify essential audit fields
        assert "inventory_item_id" in call_kwargs
        assert "movement_type" in call_kwargs
        assert "quantity_before" in call_kwargs
        assert "quantity_after" in call_kwargs
        assert "user_id" in call_kwargs

