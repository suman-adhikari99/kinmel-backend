"""
Inventory Domain Models
-----------------------
Core entities for tracking stock levels, movements, and locations.

🏪 GROCERY INVENTORY CONTEXT:
- Stock exists at specific locations (cold storage, floor, backroom)
- Perishables have expiry dates and require FIFO handling
- Stock changes must be auditable (who changed what, when, why)
- Concurrent access by multiple staff is common

🔒 SAFETY INVARIANTS:
- physical_stock >= 0 (enforced at DB level)
- buffer >= 0 (enforced at DB level)
- online_available = max(physical_stock - buffer, 0) (derived, never stored)
- SKU is immutable after creation
- All stock changes create a StockMovement audit record
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.models import BaseModel, SoftDeleteMixin, VersionedMixin

if TYPE_CHECKING:
    from src.modules.products.models import Product


# ═══════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════

class LocationType(StrEnum):
    """Types of storage locations in a grocery store."""
    
    FLOOR = "floor"              # Customer-accessible shelves
    COLD_STORAGE = "cold_storage"  # Refrigerated/frozen storage
    BACKROOM = "backroom"        # Back-of-store storage
    RECEIVING = "receiving"      # Incoming goods area
    DAMAGED = "damaged"          # Damaged goods holding area


class MovementType(StrEnum):
    """
    Types of stock movements.
    
    Each movement type has specific business rules:
    - RECEIVING: Increases stock (from suppliers)
    - SALE: Decreases stock (customer purchases)
    - TRANSFER: Moves between locations (net zero)
    - ADJUSTMENT: Manual corrections (shrinkage, counting errors)
    - RETURN: Customer returns (increases stock)
    - DISPOSAL: Expired/damaged removal (decreases stock)
    - RESERVATION: Reserved for online orders (affects buffer)
    """
    
    RECEIVING = "receiving"
    SALE = "sale"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    DISPOSAL = "disposal"
    RESERVATION = "reservation"


class MovementReason(StrEnum):
    """Standardized reasons for stock adjustments."""
    
    # Receiving
    SUPPLIER_DELIVERY = "supplier_delivery"
    INTERNAL_TRANSFER = "internal_transfer"
    
    # Decreases
    CUSTOMER_SALE = "customer_sale"
    EXPIRED = "expired"
    DAMAGED = "damaged"
    THEFT = "theft"
    SHRINKAGE = "shrinkage"
    
    # Adjustments
    CYCLE_COUNT = "cycle_count"
    AUDIT_CORRECTION = "audit_correction"
    SYSTEM_CORRECTION = "system_correction"
    
    # Other
    CUSTOMER_RETURN = "customer_return"
    ONLINE_RESERVATION = "online_reservation"
    RESERVATION_RELEASED = "reservation_released"


# ═══════════════════════════════════════════════════════════════════
# LOCATION MODEL
# ═══════════════════════════════════════════════════════════════════

class Location(BaseModel, SoftDeleteMixin):
    """
    Physical storage location within the store.
    
    Examples:
    - "FLOOR-A1" (Aisle 1 floor shelves)
    - "COLD-01" (Refrigerator unit 1)
    - "BACK-DAIRY" (Backroom dairy section)
    
    Attributes:
        code: Unique, human-readable location code
        name: Display name for staff
        location_type: Category of location
        capacity: Maximum units this location can hold (optional)
        temperature_zone: For cold storage compliance tracking
    """
    
    __tablename__ = "locations"
    
    __table_args__ = (
        UniqueConstraint("code", name="uq_locations_code"),
        Index("ix_locations_type", "location_type"),
    )
    
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        doc="Unique location code (e.g., 'FLOOR-A1', 'COLD-01')",
    )
    
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Human-readable location name",
    )
    
    location_type: Mapped[LocationType] = mapped_column(
        String(20),
        nullable=False,
        doc="Type of storage location",
    )
    
    capacity: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum units capacity (null = unlimited)",
    )
    
    temperature_zone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc="Temperature zone for cold storage (e.g., 'frozen', 'chilled')",
    )
    
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Additional notes about this location",
    )
    
    # Relationships
    inventory_items: Mapped[list["InventoryItem"]] = relationship(
        back_populates="location",
        lazy="selectin",
    )
    
    def __repr__(self) -> str:
        return f"<Location(code={self.code}, type={self.location_type})>"


# ═══════════════════════════════════════════════════════════════════
# INVENTORY ITEM MODEL (Core Model)
# ═══════════════════════════════════════════════════════════════════

class InventoryItem(BaseModel, SoftDeleteMixin, VersionedMixin):
    """
    Stock level for a product at a specific location.
    
    🔑 KEY DESIGN DECISIONS:
    
    1. LOCATION-SPECIFIC STOCK
       Same product can exist in multiple locations. Each location
       has its own InventoryItem record. This enables:
       - FIFO by location (sell from floor before backroom)
       - Location-specific buffers (floor needs safety stock)
       - Accurate capacity tracking per location
    
    2. DERIVED online_available
       `online_available = max(physical_stock - buffer, 0)`
       This is a @hybrid_property, computed on read, never stored.
       Why? Single source of truth. No sync issues between fields.
    
    3. OPTIMISTIC LOCKING (version field)
       Prevents lost updates when two staff adjust simultaneously:
       - Staff A reads stock=10, version=1
       - Staff B reads stock=10, version=1
       - Staff B saves stock=8, version=2 ✓
       - Staff A tries to save stock=15, version=2 → FAILS (expected version=1)
       Staff A must refresh and retry with current data.
    
    4. IMMUTABLE SKU REFERENCE
       SKU is stored as foreign key to Product. Once created, the
       product_id cannot change. This maintains audit integrity.
    
    5. BATCH TRACKING (via InventoryBatch)
       Perishables are tracked by batch with expiry dates.
       physical_stock here is the SUM of all active batch quantities.
    
    Attributes:
        product_id: FK to Product (contains the SKU)
        location_id: FK to Location
        physical_stock: Actual units on hand (≥ 0)
        buffer: Reserved/safety stock (≥ 0)
        reorder_point: When to trigger reorder alert
        max_stock: Maximum stock level for this location
        version: Optimistic locking counter
    """
    
    __tablename__ = "inventory_items"
    
    __table_args__ = (
        # Unique constraint: one record per product-location combination
        UniqueConstraint(
            "product_id", "location_id",
            name="uq_inventory_product_location"
        ),
        
        # Database-level enforcement of non-negative values
        # These CANNOT be bypassed by application code
        CheckConstraint(
            "physical_stock >= 0",
            name="ck_inventory_physical_stock_non_negative"
        ),
        CheckConstraint(
            "buffer >= 0",
            name="ck_inventory_buffer_non_negative"
        ),
        CheckConstraint(
            "reorder_point >= 0",
            name="ck_inventory_reorder_point_non_negative"
        ),
        
        # Indexes for common queries
        Index("ix_inventory_product_id", "product_id"),
        Index("ix_inventory_location_id", "location_id"),
        Index("ix_inventory_low_stock", "physical_stock", "reorder_point"),
    )
    
    # ─────────────────────────────────────────────────────────────
    # Foreign Keys
    # ─────────────────────────────────────────────────────────────
    
    product_id: Mapped[str] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        doc="Reference to product (contains SKU). Cannot be changed after creation.",
    )
    
    location_id: Mapped[str] = mapped_column(
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
        doc="Reference to storage location.",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Stock Fields
    # ─────────────────────────────────────────────────────────────
    
    physical_stock: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Actual units physically present. Must be ≥ 0.",
    )
    
    buffer: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Reserved stock (safety stock + online reservations). Must be ≥ 0.",
    )
    
    reorder_point: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        doc="Stock level that triggers reorder alert.",
    )
    
    max_stock: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Maximum stock for this location (null = no limit).",
    )
    
    # ─────────────────────────────────────────────────────────────
    # Relationships
    # ─────────────────────────────────────────────────────────────
    
    product: Mapped["Product"] = relationship(
        back_populates="inventory_items",
        lazy="joined",  # Usually need product info with inventory
    )
    
    location: Mapped["Location"] = relationship(
        back_populates="inventory_items",
        lazy="joined",
    )
    
    batches: Mapped[list["InventoryBatch"]] = relationship(
        back_populates="inventory_item",
        lazy="selectin",
        order_by="InventoryBatch.expiry_date.asc()",  # FIFO by expiry
    )
    
    movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="inventory_item",
        lazy="noload",  # Load explicitly when needed
    )
    
    # ─────────────────────────────────────────────────────────────
    # Computed Properties
    # ─────────────────────────────────────────────────────────────
    
    @hybrid_property
    def online_available(self) -> int:
        """
        Stock available for online orders.
        
        Formula: max(physical_stock - buffer, 0)
        
        This is a DERIVED field, never stored in the database.
        Always computed from physical_stock and buffer.
        
        Why not store it?
        - Single source of truth (no sync issues)
        - Always consistent with actual stock
        - Simpler updates (change one field, not two)
        """
        return max(self.physical_stock - self.buffer, 0)
    
    @hybrid_property
    def is_low_stock(self) -> bool:
        """Check if stock is at or below reorder point."""
        return self.physical_stock <= self.reorder_point
    
    @hybrid_property
    def is_out_of_stock(self) -> bool:
        """Check if no stock is available."""
        return self.physical_stock == 0
    
    # ─────────────────────────────────────────────────────────────
    # Business Methods
    # ─────────────────────────────────────────────────────────────
    
    def can_fulfill(self, quantity: int) -> bool:
        """
        Check if we can fulfill a quantity from available stock.
        
        Uses online_available, not physical_stock, because buffer
        is reserved for other purposes.
        """
        return self.online_available >= quantity
    
    def adjust_stock(
        self,
        quantity_delta: int,
        reason: str | None = None,
    ) -> None:
        """
        Adjust physical stock by a delta amount.
        
        Args:
            quantity_delta: Amount to add (positive) or remove (negative)
            reason: Optional reason for the adjustment
            
        Raises:
            ValueError: If adjustment would make stock negative
            
        Note:
            This method updates the version for optimistic locking.
            The actual StockMovement record should be created by the service layer.
        """
        new_stock = self.physical_stock + quantity_delta
        
        if new_stock < 0:
            raise ValueError(
                f"Cannot reduce stock below 0. "
                f"Current: {self.physical_stock}, Delta: {quantity_delta}"
            )
        
        self.physical_stock = new_stock
        self.increment_version()
    
    def adjust_buffer(self, quantity_delta: int) -> None:
        """
        Adjust buffer stock by a delta amount.
        
        Args:
            quantity_delta: Amount to add (positive) or remove (negative)
            
        Raises:
            ValueError: If adjustment would make buffer negative
        """
        new_buffer = self.buffer + quantity_delta
        
        if new_buffer < 0:
            raise ValueError(
                f"Cannot reduce buffer below 0. "
                f"Current: {self.buffer}, Delta: {quantity_delta}"
            )
        
        self.buffer = new_buffer
        self.increment_version()
    
    def __repr__(self) -> str:
        return (
            f"<InventoryItem("
            f"product_id={self.product_id}, "
            f"location_id={self.location_id}, "
            f"stock={self.physical_stock}, "
            f"buffer={self.buffer}, "
            f"available={self.online_available}"
            f")>"
        )


# ═══════════════════════════════════════════════════════════════════
# INVENTORY BATCH MODEL (Expiry Tracking)
# ═══════════════════════════════════════════════════════════════════

class InventoryBatch(BaseModel):
    """
    Batch tracking for perishable inventory.
    
    🥛 GROCERY CONTEXT:
    Perishables must be sold FIFO by expiry date. Each batch represents
    a delivery with a specific expiry date. When selling, we decrement
    from the batch with the earliest expiry first.
    
    Example:
    - Batch A: 20 units, expires 2024-01-15
    - Batch B: 30 units, expires 2024-01-20
    - Sale of 25 units → Take 20 from A, 5 from B
    
    Attributes:
        inventory_item_id: Parent inventory record
        batch_number: Supplier batch/lot number
        quantity: Units remaining in this batch
        expiry_date: When this batch expires
        received_date: When we received this batch
        cost_per_unit: Purchase cost (for margin tracking)
    """
    
    __tablename__ = "inventory_batches"
    
    __table_args__ = (
        CheckConstraint(
            "quantity >= 0",
            name="ck_batch_quantity_non_negative"
        ),
        Index("ix_batch_expiry", "expiry_date"),
        Index("ix_batch_inventory_item", "inventory_item_id"),
    )
    
    inventory_item_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    
    batch_number: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="Supplier batch/lot number for traceability",
    )
    
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Units remaining in this batch",
    )
    
    expiry_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Expiration date (null for non-perishables)",
    )
    
    received_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        doc="When this batch was received",
    )
    
    cost_per_unit: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        doc="Purchase cost per unit for margin analysis",
    )
    
    # Relationships
    inventory_item: Mapped["InventoryItem"] = relationship(
        back_populates="batches",
    )
    
    @hybrid_property
    def is_expired(self) -> bool:
        """Check if this batch has expired."""
        if self.expiry_date is None:
            return False
        return datetime.now(UTC) > self.expiry_date
    
    @hybrid_property
    def days_until_expiry(self) -> int | None:
        """Days until expiry (negative if already expired)."""
        if self.expiry_date is None:
            return None
        delta = self.expiry_date - datetime.now(UTC)
        return delta.days
    
    def __repr__(self) -> str:
        return (
            f"<InventoryBatch("
            f"batch={self.batch_number}, "
            f"qty={self.quantity}, "
            f"expires={self.expiry_date}"
            f")>"
        )


# ═══════════════════════════════════════════════════════════════════
# STOCK MOVEMENT MODEL (Audit Trail)
# ═══════════════════════════════════════════════════════════════════

class StockMovement(BaseModel):
    """
    Immutable audit record of every stock change.
    
    📋 AUDIT REQUIREMENTS:
    Every change to inventory must be traceable:
    - Who made the change (user_id)
    - When it happened (created_at)
    - What changed (quantity_before, quantity_after)
    - Why it changed (movement_type, reason, notes)
    - Correlation for related changes (reference_id)
    
    🔒 IMMUTABILITY:
    StockMovement records are NEVER updated or deleted.
    They form an append-only audit log. If a correction is needed,
    a new movement is created (e.g., ADJUSTMENT type).
    
    Attributes:
        inventory_item_id: Which inventory record changed
        movement_type: Category of movement
        reason: Standardized reason code
        quantity_delta: Amount changed (+/-)
        quantity_before: Stock level before change
        quantity_after: Stock level after change
        user_id: Who made the change
        reference_id: Link to related record (order, transfer, etc.)
        notes: Free-text notes from staff
    """
    
    __tablename__ = "stock_movements"
    
    __table_args__ = (
        Index("ix_movement_inventory_item", "inventory_item_id"),
        Index("ix_movement_type", "movement_type"),
        Index("ix_movement_created_at", "created_at"),
        Index("ix_movement_user", "user_id"),
        Index("ix_movement_reference", "reference_id"),
    )
    
    inventory_item_id: Mapped[str] = mapped_column(
        ForeignKey("inventory_items.id", ondelete="RESTRICT"),
        nullable=False,
        doc="The inventory record that changed",
    )
    
    movement_type: Mapped[MovementType] = mapped_column(
        String(20),
        nullable=False,
        doc="Type of stock movement",
    )
    
    reason: Mapped[MovementReason | None] = mapped_column(
        String(30),
        nullable=True,
        doc="Standardized reason code",
    )
    
    quantity_delta: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Amount changed (positive = increase, negative = decrease)",
    )
    
    quantity_before: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Stock level before this change",
    )
    
    quantity_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        doc="Stock level after this change",
    )
    
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        doc="User who performed this action",
    )
    
    reference_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        doc="Reference to related record (order ID, transfer ID, etc.)",
    )
    
    reference_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        doc="Type of reference (order, transfer, disposal_request, etc.)",
    )
    
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Staff notes explaining the change",
    )
    
    # Batch tracking for FIFO
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("inventory_batches.id", ondelete="SET NULL"),
        nullable=True,
        doc="Which batch was affected (for perishables)",
    )
    
    # Relationships
    inventory_item: Mapped["InventoryItem"] = relationship(
        back_populates="movements",
    )
    
    @hybrid_property
    def is_increase(self) -> bool:
        """Was this an increase in stock?"""
        return self.quantity_delta > 0
    
    @hybrid_property
    def is_decrease(self) -> bool:
        """Was this a decrease in stock?"""
        return self.quantity_delta < 0
    
    def __repr__(self) -> str:
        return (
            f"<StockMovement("
            f"type={self.movement_type}, "
            f"delta={self.quantity_delta:+d}, "
            f"{self.quantity_before}→{self.quantity_after}"
            f")>"
        )

