"""
Inventory Service
-----------------
Business logic layer for inventory operations.

🎯 RESPONSIBILITIES:
1. Orchestrate complex operations (multiple repo calls in single transaction)
2. Enforce business rules that span multiple entities
3. Create audit records (StockMovement) for every change
4. Handle failure modes gracefully with clear error messages

🔒 CONCURRENCY SAFETY:
All stock mutations follow this pattern:
1. Load item (with version)
2. Validate business rules
3. Calculate new values
4. Update with optimistic lock (version check)
5. Create audit record
6. Commit or rollback as atomic unit

If step 4 fails (version mismatch), the entire operation fails
and the caller should retry with fresh data.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.exceptions import (
    ConcurrencyError,
    InsufficientStockError,
    NotFoundError,
    StockAdjustmentTooLargeError,
    ValidationError,
)
from src.core.logging import LoggerMixin
from src.modules.inventory.models import (
    InventoryBatch,
    InventoryItem,
    Location,
    LocationType,
    MovementReason,
    MovementType,
    StockMovement,
)
from src.modules.inventory.repository import InventoryRepository, inventory_repository
from src.modules.products.category_repository import category_repository
from src.modules.notifications.service import notifications_service

settings = get_settings()


# ═══════════════════════════════════════════════════════════════════════════
# DATA TRANSFER OBJECTS (DTOs)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class StockOperationResult:
    """
    Result of a stock operation.
    
    Immutable dataclass returned from all stock operations.
    Contains the updated inventory state and audit record.
    """
    
    inventory_item: InventoryItem
    movement: StockMovement
    previous_stock: int
    new_stock: int
    
    @property
    def delta(self) -> int:
        """Stock change amount."""
        return self.new_stock - self.previous_stock


@dataclass(frozen=True)
class ReceivingInput:
    """Input for stock receiving operation."""
    
    sku: str
    location_id: str
    quantity: int
    user_id: str
    batch_number: str | None = None
    expiry_date: datetime | None = None
    cost_per_unit: Decimal | None = None
    reference_id: str | None = None  # PO number, delivery note, etc.
    notes: str | None = None


@dataclass(frozen=True)
class AdjustmentInput:
    """Input for stock adjustment operation."""
    
    sku: str
    location_id: str
    new_quantity: int  # Absolute value, not delta
    user_id: str
    reason: MovementReason
    notes: str | None = None
    skip_large_adjustment_check: bool = False  # For manager overrides


@dataclass(frozen=True)
class ReservationInput:
    """Input for stock reservation (online orders)."""
    
    sku: str
    location_id: str
    quantity: int
    user_id: str
    order_id: str  # Reference to the order
    notes: str | None = None


# ═══════════════════════════════════════════════════════════════════════════
# INVENTORY SERVICE
# ═══════════════════════════════════════════════════════════════════════════

class InventoryService(LoggerMixin):
    """
    Inventory business logic service.
    
    All methods are async and expect a database session.
    Transaction management is the caller's responsibility,
    but this service ensures atomicity of its operations.
    """
    
    def __init__(self, repository: InventoryRepository | None = None):
        self.repo = repository or inventory_repository

    def _is_uuid(self, value: str) -> bool:
        try:
            UUID(value)
            return True
        except ValueError:
            return False

    async def _resolve_location_id(
        self,
        session: AsyncSession,
        location_id: str | None,
    ) -> str | None:
        if location_id:
            return location_id
        return await self.repo.get_default_location_id(session)

    async def ensure_inventory_item(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str,
        product_id: str | None = None,
        initial_physical_stock: int = 0,
        initial_buffer: int = 0,
        initial_reorder_point: int = 0,
        initial_max_stock: int | None = None,
    ) -> tuple[InventoryItem, bool]:
        """
        Ensure an inventory item exists for a SKU/location.

        Returns the item and a flag indicating whether it was created or reactivated.
        """
        if initial_physical_stock < 0:
            raise ValidationError("physical_stock", "Stock cannot be negative")
        if initial_buffer < 0:
            raise ValidationError("buffer", "Buffer cannot be negative")
        if initial_reorder_point < 0:
            raise ValidationError("reorder_point", "Reorder point cannot be negative")

        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            location_id,
        )
        if item is not None:
            return item, False

        resolved_product_id = product_id
        if not resolved_product_id:
            from src.modules.products.repository import product_repository

            product = await product_repository.get_by_sku(session, sku)
            if product is None:
                raise NotFoundError(
                    "Product",
                    sku,
                    staff_message="Product not found.",
                    details={"resource": "Product", "identifier": sku},
                )
            resolved_product_id = product.id

        created = await self.repo.create_if_missing(
            session,
            product_id=resolved_product_id,
            location_id=location_id,
            physical_stock=initial_physical_stock,
            buffer=initial_buffer,
            reorder_point=initial_reorder_point,
            max_stock=initial_max_stock,
        )

        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            location_id,
            for_update=True,
            include_inactive=True,
        )
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
        if not item.is_active:
            item.is_active = True
            item.deleted_at = None
            await session.flush()
            created = True

        return item, created

    async def list_locations(
        self,
        session: AsyncSession,
        *,
        location_type: LocationType | None = None,
    ) -> Sequence[Location]:
        return await self.repo.list_locations(session, location_type=location_type)

    async def get_location_by_code(
        self,
        session: AsyncSession,
        code: str,
    ) -> Location:
        normalized = code.strip().upper()
        location = await self.repo.get_location_by_code(session, normalized)
        if not location:
            raise NotFoundError("Location", normalized)
        return location

    async def _emit_stock_notification(
        self,
        session: AsyncSession,
        *,
        item: InventoryItem,
        previous_stock: int,
        new_stock: int,
    ) -> None:
        if previous_stock <= 0 and new_stock <= 0:
            return

        reorder_point = item.reorder_point
        is_out_of_stock = previous_stock > 0 and new_stock == 0
        is_newly_low = (
            reorder_point > 0
            and previous_stock > reorder_point
            and new_stock <= reorder_point
            and new_stock > 0
        )

        if not (is_out_of_stock or is_newly_low):
            return

        product_name = item.product.name if item.product else "Item"
        sku = item.product.sku if item.product else "unknown"
        location = item.location.code if item.location else "location"

        if is_out_of_stock:
            await notifications_service.create_notification(
                session,
                notif_type="alert",
                title=f"Out of Stock: {sku}",
                message=f"{product_name} at {location} is out of stock.",
                source_label="Open inventory",
                source_href=f"/dashboard/inventory?sku={sku}",
            )
            return

        await notifications_service.create_notification(
            session,
            notif_type="stock",
            title=f"Low Stock: {sku}",
            message=(
                f"{product_name} at {location} is low — {new_stock} left "
                f"(reorder point {reorder_point})."
            ),
            source_label="Open inventory",
            source_href=f"/dashboard/inventory?sku={sku}",
        )
    
    # ───────────────────────────────────────────────────────────────────
    # RECEIVING STOCK (Goods In)
    # ───────────────────────────────────────────────────────────────────
    
    async def receive_stock(
        self,
        session: AsyncSession,
        input_data: ReceivingInput,
    ) -> StockOperationResult:
        """
        Receive new stock into inventory.
        
        Use cases:
        - Supplier delivery
        - Transfer from another store
        - Return from customer
        
        Creates:
        - InventoryItem if first time at this location
        - InventoryBatch if expiry_date provided (perishables)
        - StockMovement audit record
        
        Args:
            session: Database session
            input_data: Receiving details
            
        Returns:
            StockOperationResult with updated state
            
        Raises:
            ValidationError: Invalid input (negative quantity, etc.)
            NotFoundError: Location not found
        """
        # ─────────────────────────────────────────────────────────────
        # Validation
        # ─────────────────────────────────────────────────────────────
        if input_data.quantity <= 0:
            raise ValidationError("quantity", "Quantity must be positive")
        
        # ─────────────────────────────────────────────────────────────
        # Load or create inventory item
        # ─────────────────────────────────────────────────────────────
        item = await self.repo.get_by_sku_and_location(
            session,
            input_data.sku,
            input_data.location_id,
            for_update=True,  # Lock for update
        )
        
        if item is None:
            # First time receiving this SKU at this location
            # Need to look up the product first
            from src.modules.products.repository import product_repository
            
            product = await product_repository.get_by_sku(session, input_data.sku)
            if product is None:
                raise NotFoundError("Product", input_data.sku)
            
            item = await self.repo.create(
                session,
                product_id=product.id,
                location_id=input_data.location_id,
                physical_stock=0,
            )
        
        # ─────────────────────────────────────────────────────────────
        # Calculate new values
        # ─────────────────────────────────────────────────────────────
        previous_stock = item.physical_stock
        new_stock = previous_stock + input_data.quantity
        expected_version = item.version
        
        # ─────────────────────────────────────────────────────────────
        # Update with optimistic lock
        # ─────────────────────────────────────────────────────────────
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=new_stock,
            expected_version=expected_version,
        )
        
        # ─────────────────────────────────────────────────────────────
        # Create batch if perishable
        # ─────────────────────────────────────────────────────────────
        batch: InventoryBatch | None = None
        if input_data.expiry_date is not None:
            batch = await self.repo.create_batch(
                session,
                inventory_item_id=item.id,
                quantity=input_data.quantity,
                batch_number=input_data.batch_number,
                expiry_date=input_data.expiry_date,
                cost_per_unit=float(input_data.cost_per_unit) if input_data.cost_per_unit else None,
            )
        
        # ─────────────────────────────────────────────────────────────
        # Create audit record
        # ─────────────────────────────────────────────────────────────
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.RECEIVING,
            reason=MovementReason.SUPPLIER_DELIVERY,
            quantity_delta=input_data.quantity,
            quantity_before=previous_stock,
            quantity_after=new_stock,
            user_id=input_data.user_id,
            reference_id=input_data.reference_id,
            reference_type="purchase_order",
            notes=input_data.notes,
            batch_id=batch.id if batch else None,
        )
        
        self.logger.info(
            "Stock received",
            sku=input_data.sku,
            location=input_data.location_id,
            quantity=input_data.quantity,
            new_stock=new_stock,
            user=input_data.user_id,
        )
        
        # Refresh item to get updated values
        await session.refresh(item)

        await self._emit_stock_notification(
            session,
            item=item,
            previous_stock=previous_stock,
            new_stock=input_data.new_quantity,
        )
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=previous_stock,
            new_stock=new_stock,
        )
    
    # ───────────────────────────────────────────────────────────────────
    # STOCK ADJUSTMENT (Manual Corrections)
    # ───────────────────────────────────────────────────────────────────
    
    async def adjust_stock(
        self,
        session: AsyncSession,
        input_data: AdjustmentInput,
    ) -> StockOperationResult:
        """
        Manually adjust stock to a new absolute value.
        
        Use cases:
        - Cycle count corrections
        - Shrinkage recording
        - Damage write-offs
        - Audit corrections
        
        🛡️ SAFETY FEATURE:
        Large adjustments (>50% of current stock) are blocked by default.
        This prevents accidental typos (e.g., 1000 instead of 100).
        Managers can override with skip_large_adjustment_check=True.
        
        Args:
            session: Database session
            input_data: Adjustment details
            
        Returns:
            StockOperationResult
            
        Raises:
            NotFoundError: Item not found
            ValidationError: Invalid input
            StockAdjustmentTooLargeError: Adjustment exceeds safety threshold
            ConcurrencyError: Version mismatch
        """
        # ─────────────────────────────────────────────────────────────
        # Validation
        # ─────────────────────────────────────────────────────────────
        if input_data.new_quantity < 0:
            raise ValidationError("new_quantity", "Stock cannot be negative")
        
        # ─────────────────────────────────────────────────────────────
        # Load item with lock
        # ─────────────────────────────────────────────────────────────
        item = await self.repo.get_by_sku_and_location(
            session,
            input_data.sku,
            input_data.location_id,
            for_update=True,
        )
        
        if item is None:
            raise NotFoundError("InventoryItem", f"{input_data.sku}@{input_data.location_id}")
        
        previous_stock = item.physical_stock
        delta = input_data.new_quantity - previous_stock
        
        # ─────────────────────────────────────────────────────────────
        # Large adjustment safety check
        # ─────────────────────────────────────────────────────────────
        if not input_data.skip_large_adjustment_check and previous_stock > 0:
            threshold_percent = settings.max_stock_adjustment_percent
            max_delta = int(previous_stock * threshold_percent / 100)
            
            if abs(delta) > max_delta:
                raise StockAdjustmentTooLargeError(
                    sku=input_data.sku,
                    adjustment=delta,
                    threshold_percent=threshold_percent,
                )
        
        # ─────────────────────────────────────────────────────────────
        # Update with optimistic lock
        # ─────────────────────────────────────────────────────────────
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=input_data.new_quantity,
            expected_version=item.version,
        )
        
        # ─────────────────────────────────────────────────────────────
        # Create audit record
        # ─────────────────────────────────────────────────────────────
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.ADJUSTMENT,
            reason=input_data.reason,
            quantity_delta=delta,
            quantity_before=previous_stock,
            quantity_after=input_data.new_quantity,
            user_id=input_data.user_id,
            notes=input_data.notes,
        )
        
        self.logger.info(
            "Stock adjusted",
            sku=input_data.sku,
            location=input_data.location_id,
            previous=previous_stock,
            new=input_data.new_quantity,
            delta=delta,
            reason=input_data.reason,
            user=input_data.user_id,
        )
        
        await session.refresh(item)

        await self._emit_stock_notification(
            session,
            item=item,
            previous_stock=previous_stock,
            new_stock=input_data.new_quantity,
        )
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=previous_stock,
            new_stock=input_data.new_quantity,
        )
    
    # ───────────────────────────────────────────────────────────────────
    # STOCK RESERVATION (Online Orders)
    # ───────────────────────────────────────────────────────────────────
    
    async def reserve_stock(
        self,
        session: AsyncSession,
        input_data: ReservationInput,
    ) -> StockOperationResult:
        """
        Reserve stock for an online order.
        
        Reservations increase the buffer, reducing online_available.
        Physical stock stays the same until the order is fulfilled.
        
        Formula:
        - buffer += quantity
        - online_available = physical_stock - buffer (decreases)
        
        Args:
            session: Database session
            input_data: Reservation details
            
        Returns:
            StockOperationResult
            
        Raises:
            NotFoundError: Item not found
            InsufficientStockError: Not enough online_available
            ConcurrencyError: Version mismatch
        """
        # ─────────────────────────────────────────────────────────────
        # Validation
        # ─────────────────────────────────────────────────────────────
        if input_data.quantity <= 0:
            raise ValidationError("quantity", "Quantity must be positive")
        
        # ─────────────────────────────────────────────────────────────
        # Load item with lock
        # ─────────────────────────────────────────────────────────────
        item = await self.repo.get_by_sku_and_location(
            session,
            input_data.sku,
            input_data.location_id,
            for_update=True,
        )
        
        if item is None:
            raise NotFoundError("InventoryItem", f"{input_data.sku}@{input_data.location_id}")
        
        # ─────────────────────────────────────────────────────────────
        # Check availability
        # ─────────────────────────────────────────────────────────────
        if not item.can_fulfill(input_data.quantity):
            raise InsufficientStockError(
                sku=input_data.sku,
                requested=input_data.quantity,
                available=item.online_available,
            )
        
        # ─────────────────────────────────────────────────────────────
        # Update buffer (not physical stock)
        # ─────────────────────────────────────────────────────────────
        previous_buffer = item.buffer
        new_buffer = previous_buffer + input_data.quantity
        
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=item.physical_stock,  # Unchanged
            new_buffer=new_buffer,
            expected_version=item.version,
        )
        
        # ─────────────────────────────────────────────────────────────
        # Create audit record
        # ─────────────────────────────────────────────────────────────
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.RESERVATION,
            reason=MovementReason.ONLINE_RESERVATION,
            quantity_delta=0,  # Physical stock unchanged
            quantity_before=item.physical_stock,
            quantity_after=item.physical_stock,
            user_id=input_data.user_id,
            reference_id=input_data.order_id,
            reference_type="order",
            notes=f"Reserved {input_data.quantity} units. Buffer: {previous_buffer} → {new_buffer}",
        )
        
        self.logger.info(
            "Stock reserved",
            sku=input_data.sku,
            location=input_data.location_id,
            quantity=input_data.quantity,
            order_id=input_data.order_id,
            new_buffer=new_buffer,
            new_online_available=item.physical_stock - new_buffer,
        )
        
        await session.refresh(item)
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=item.physical_stock,
            new_stock=item.physical_stock,  # Physical unchanged
        )
    
    # ───────────────────────────────────────────────────────────────────
    # RELEASE RESERVATION (Cancel/Expire Order)
    # ───────────────────────────────────────────────────────────────────
    
    async def release_reservation(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str,
        quantity: int,
        user_id: str,
        order_id: str,
        notes: str | None = None,
    ) -> StockOperationResult:
        """
        Release a stock reservation.
        
        Called when:
        - Order is cancelled
        - Order reservation expires
        - Order is fulfilled (combined with stock decrement)
        
        Args:
            session: Database session
            sku: Product SKU
            location_id: Location UUID
            quantity: Units to release
            user_id: User performing action
            order_id: Original order reference
            notes: Optional notes
            
        Returns:
            StockOperationResult
        """
        if quantity <= 0:
            raise ValidationError("quantity", "Quantity must be positive")
        
        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            location_id,
            for_update=True,
        )
        
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
        
        # Can't release more than buffered
        if quantity > item.buffer:
            raise ValidationError(
                "quantity",
                f"Cannot release {quantity} units. Only {item.buffer} buffered.",
            )
        
        previous_buffer = item.buffer
        new_buffer = previous_buffer - quantity
        
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=item.physical_stock,
            new_buffer=new_buffer,
            expected_version=item.version,
        )
        
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.RESERVATION,
            reason=MovementReason.RESERVATION_RELEASED,
            quantity_delta=0,
            quantity_before=item.physical_stock,
            quantity_after=item.physical_stock,
            user_id=user_id,
            reference_id=order_id,
            reference_type="order",
            notes=notes or f"Released {quantity} units. Buffer: {previous_buffer} → {new_buffer}",
        )
        
        self.logger.info(
            "Reservation released",
            sku=sku,
            location=location_id,
            quantity=quantity,
            order_id=order_id,
            new_buffer=new_buffer,
        )
        
        await session.refresh(item)
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=item.physical_stock,
            new_stock=item.physical_stock,
        )
    
    # ───────────────────────────────────────────────────────────────────
    # FULFILL ORDER (Decrement Stock)
    # ───────────────────────────────────────────────────────────────────
    
    async def fulfill_order(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str,
        quantity: int,
        user_id: str,
        order_id: str,
        notes: str | None = None,
    ) -> StockOperationResult:
        """
        Fulfill an order by decrementing stock.
        
        This is a SALE operation:
        - Decreases physical_stock
        - Decreases buffer (releases reservation)
        
        For reserved orders, buffer and physical both decrease.
        For walk-in sales (no reservation), only physical decreases.
        
        Args:
            session: Database session
            sku: Product SKU
            location_id: Location UUID
            quantity: Units sold
            user_id: User performing action
            order_id: Order reference
            notes: Optional notes
        """
        if quantity <= 0:
            raise ValidationError("quantity", "Quantity must be positive")
        
        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            location_id,
            for_update=True,
        )
        
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
        
        if item.physical_stock < quantity:
            raise InsufficientStockError(
                sku=sku,
                requested=quantity,
                available=item.physical_stock,
            )
        
        previous_stock = item.physical_stock
        new_stock = previous_stock - quantity
        
        # If there's a buffer, reduce it too (releasing the reservation)
        previous_buffer = item.buffer
        buffer_reduction = min(quantity, item.buffer)
        new_buffer = previous_buffer - buffer_reduction
        
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=new_stock,
            new_buffer=new_buffer,
            expected_version=item.version,
        )
        
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.SALE,
            reason=MovementReason.CUSTOMER_SALE,
            quantity_delta=-quantity,
            quantity_before=previous_stock,
            quantity_after=new_stock,
            user_id=user_id,
            reference_id=order_id,
            reference_type="order",
            notes=notes,
        )
        
        self.logger.info(
            "Order fulfilled",
            sku=sku,
            location=location_id,
            quantity=quantity,
            order_id=order_id,
            new_stock=new_stock,
        )
        
        await session.refresh(item)

        await self._emit_stock_notification(
            session,
            item=item,
            previous_stock=previous_stock,
            new_stock=new_stock,
        )
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=previous_stock,
            new_stock=new_stock,
        )
    
    # ───────────────────────────────────────────────────────────────────
    # DISPOSAL (Expired/Damaged)
    # ───────────────────────────────────────────────────────────────────
    
    async def dispose_stock(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str,
        quantity: int,
        user_id: str,
        reason: MovementReason,
        batch_id: str | None = None,
        notes: str | None = None,
    ) -> StockOperationResult:
        """
        Dispose of stock (expired, damaged, etc.).
        
        Args:
            session: Database session
            sku: Product SKU
            location_id: Location UUID
            quantity: Units to dispose
            user_id: User performing action
            reason: Disposal reason (EXPIRED, DAMAGED, etc.)
            batch_id: Specific batch being disposed
            notes: Required notes explaining disposal
        """
        if quantity <= 0:
            raise ValidationError("quantity", "Quantity must be positive")
        
        if reason not in (MovementReason.EXPIRED, MovementReason.DAMAGED, MovementReason.SHRINKAGE):
            raise ValidationError("reason", "Invalid disposal reason")
        
        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            location_id,
            for_update=True,
        )
        
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
        
        if item.physical_stock < quantity:
            raise InsufficientStockError(
                sku=sku,
                requested=quantity,
                available=item.physical_stock,
            )
        
        previous_stock = item.physical_stock
        new_stock = previous_stock - quantity
        
        await self.repo.update_stock_optimistic(
            session,
            item.id,
            new_physical_stock=new_stock,
            expected_version=item.version,
        )
        
        movement = await self.repo.create_movement(
            session,
            inventory_item_id=item.id,
            movement_type=MovementType.DISPOSAL,
            reason=reason,
            quantity_delta=-quantity,
            quantity_before=previous_stock,
            quantity_after=new_stock,
            user_id=user_id,
            batch_id=batch_id,
            notes=notes,
        )
        
        self.logger.info(
            "Stock disposed",
            sku=sku,
            location=location_id,
            quantity=quantity,
            reason=reason,
            user=user_id,
        )
        
        await session.refresh(item)

        await self._emit_stock_notification(
            session,
            item=item,
            previous_stock=previous_stock,
            new_stock=new_stock,
        )
        
        return StockOperationResult(
            inventory_item=item,
            movement=movement,
            previous_stock=previous_stock,
            new_stock=new_stock,
        )
    
    # ───────────────────────────────────────────────────────────────────
    # QUERY OPERATIONS
    # ───────────────────────────────────────────────────────────────────
    
    async def get_stock_level(
        self,
        session: AsyncSession,
        sku: str,
        location_id: str | None = None,
    ) -> dict:
        """
        Get current stock levels for a SKU.
        
        If location_id provided, returns stock at that location.
        Otherwise, returns aggregated stock across all locations.
        """
        if location_id:
            item = await self.repo.get_by_sku_and_location(session, sku, location_id)
            if item is None:
                raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
            
            return {
                "sku": sku,
                "location_id": location_id,
                "physical_stock": item.physical_stock,
                "buffer": item.buffer,
                "online_available": item.online_available,
                "is_low_stock": item.is_low_stock,
                "reorder_point": item.reorder_point,
            }
        else:
            totals = await self.repo.get_total_stock_by_sku(session, sku)
            return {
                "sku": sku,
                "location_id": None,
                "physical_stock": totals["physical_stock"],
                "buffer": totals["buffer"],
                "online_available": totals["online_available"],
            }

    async def get_inventory_summary(
        self,
        session: AsyncSession,
        *,
        location_id: str | None = None,
    ) -> dict:
        resolved_location_id = await self._resolve_location_id(session, location_id)
        return await self.repo.get_inventory_summary(
            session,
            location_id=resolved_location_id,
        )

    async def list_inventory_items(
        self,
        session: AsyncSession,
        *,
        location_id: str | None,
        search: str | None,
        category: str | None,
        status: str | None,
        low_stock_only: bool,
        out_of_stock_only: bool,
        limit: int,
        offset: int,
        sort: str,
        order: str,
    ) -> tuple[Sequence[InventoryItem], int]:
        resolved_location_id = await self._resolve_location_id(session, location_id)
        category_name = category
        if category and self._is_uuid(category):
            matched = await category_repository.get_by_id(session, category)
            if not matched:
                return [], 0
            category_name = matched.name
        return await self.repo.list_inventory_items(
            session,
            location_id=resolved_location_id,
            search=search,
            category=category_name,
            status=status,
            low_stock_only=low_stock_only,
            out_of_stock_only=out_of_stock_only,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )

    async def update_stock_level(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str | None,
        new_stock: int,
        user_id: str,
    ) -> StockOperationResult:
        resolved_location_id = await self._resolve_location_id(session, location_id)
        if not resolved_location_id:
            raise ValidationError("location_id", "No active location found")
        return await self.adjust_stock(
            session,
            AdjustmentInput(
                sku=sku,
                location_id=resolved_location_id,
                new_quantity=new_stock,
                reason=MovementReason.CYCLE_COUNT,
                notes="Inventory stock update",
                user_id=user_id,
            ),
        )

    async def update_threshold(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str | None,
        new_threshold: int,
    ) -> InventoryItem:
        resolved_location_id = await self._resolve_location_id(session, location_id)
        if not resolved_location_id:
            raise ValidationError("location_id", "No active location found")
        item = await self.repo.get_by_sku_and_location(
            session,
            sku,
            resolved_location_id,
            for_update=True,
        )
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{resolved_location_id}")
        await self.repo.update_reorder_point_optimistic(
            session,
            item.id,
            new_reorder_point=new_threshold,
            expected_version=item.version,
        )
        await session.refresh(item)
        return item

    async def get_movement_history_by_sku(
        self,
        session: AsyncSession,
        *,
        sku: str,
        location_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[Sequence[StockMovement], int]:
        resolved_location_id = await self._resolve_location_id(session, location_id)
        return await self.repo.get_movements_by_sku(
            session,
            sku=sku,
            location_id=resolved_location_id,
            limit=limit,
            offset=offset,
        )
    
    async def get_low_stock_alerts(
        self,
        session: AsyncSession,
        location_id: str | None = None,
    ) -> Sequence[InventoryItem]:
        """Get all items at or below reorder point."""
        return await self.repo.get_low_stock_items(session, location_id=location_id)
    
    async def get_expiring_soon(
        self,
        session: AsyncSession,
        days_ahead: int = 7,
        location_id: str | None = None,
    ) -> Sequence[InventoryBatch]:
        """Get batches expiring within N days."""
        return await self.repo.get_expiring_batches(
            session,
            days_ahead=days_ahead,
            location_id=location_id,
        )
    
    async def get_movement_history(
        self,
        session: AsyncSession,
        sku: str,
        location_id: str,
        *,
        limit: int = 50,
    ) -> Sequence[StockMovement]:
        """Get movement history for an item."""
        item = await self.repo.get_by_sku_and_location(session, sku, location_id)
        if item is None:
            raise NotFoundError("InventoryItem", f"{sku}@{location_id}")
        
        return await self.repo.get_movements_for_item(session, item.id, limit=limit)


# Singleton instance for dependency injection
inventory_service = InventoryService()
