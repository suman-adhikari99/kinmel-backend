"""
Inventory API Schemas
---------------------
Pydantic v2 models for request/response validation.

Design Principles:
1. Strict validation at API boundary (fail fast)
2. Clear field constraints with helpful error messages
3. Explicit typing - no implicit coercion surprises
4. Staff-friendly validation errors

Pydantic v2 Features Used:
- Field() with constraints (ge, le, min_length)
- Strict types (no "5" -> 5 coercion)
- Computed fields (@computed_field)
- Model serialization customization
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
)

from src.modules.inventory.models import (
    LocationType,
    MovementReason,
    MovementType,
)


# ═══════════════════════════════════════════════════════════════════════════
# COMMON TYPES
# ═══════════════════════════════════════════════════════════════════════════

# Annotated types for reuse
PositiveInt = Annotated[int, Field(gt=0, description="Must be greater than 0")]
NonNegativeInt = Annotated[int, Field(ge=0, description="Must be 0 or greater")]
SKU = Annotated[str, Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9\-]+$")]
LocationId = Annotated[str, Field(min_length=1, max_length=50)]


class StrictModel(BaseModel):
    """
    Base model with strict configuration.
    
    - No extra fields allowed (prevents typos)
    - Strict types (no coercion)
    - Validation on assignment
    """
    
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# ═══════════════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class ReceiveStockRequest(StrictModel):
    """
    Request to receive new stock.
    
    Used by: Receiving staff, managers
    Endpoint: POST /inventory/receive
    """
    
    sku: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Product SKU (e.g., 'MILK-2L-WHOLE')",
        examples=["MILK-2L-WHOLE", "BREAD-WHITE-LOAF"],
    )
    
    location_id: str = Field(
        ...,
        min_length=1,
        description="Target storage location ID",
    )
    
    quantity: int = Field(
        ...,
        gt=0,
        le=10000,  # Reasonable upper limit prevents accidents
        description="Number of units received",
    )
    
    batch_number: str | None = Field(
        default=None,
        max_length=100,
        description="Supplier batch/lot number (for traceability)",
    )
    
    expiry_date: datetime | None = Field(
        default=None,
        description="Expiration date for perishables (ISO 8601 format)",
    )
    
    cost_per_unit: Decimal | None = Field(
        default=None,
        ge=0,
        description="Purchase cost per unit (2 decimal places)",
    )
    
    reference_id: str | None = Field(
        default=None,
        max_length=50,
        description="Purchase order or delivery note number",
    )
    
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Additional notes about this delivery",
    )
    
    @field_validator("sku")
    @classmethod
    def validate_sku_format(cls, v: str) -> str:
        """Normalize SKU to uppercase."""
        return v.upper().strip()
    
    @field_validator("expiry_date")
    @classmethod
    def validate_expiry_future(cls, v: datetime | None) -> datetime | None:
        """Expiry date must be in the future."""
        if v is not None and v < datetime.now(v.tzinfo):
            raise ValueError("Expiry date must be in the future")
        return v


class AdjustStockRequest(StrictModel):
    """
    Request to manually adjust stock.
    
    Used by: Managers only (staff cannot adjust)
    Endpoint: POST /inventory/adjust
    
    ⚠️ SAFETY: Large adjustments (>50% of current) require confirmation.
    """
    
    sku: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Product SKU",
    )
    
    location_id: str = Field(
        ...,
        min_length=1,
        description="Storage location ID",
    )
    
    new_quantity: int = Field(
        ...,
        ge=0,
        le=100000,
        description="New absolute stock quantity (not a delta)",
    )
    
    reason: MovementReason = Field(
        ...,
        description="Reason for adjustment",
    )
    
    notes: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Explanation for this adjustment (required)",
    )
    
    confirm_large_adjustment: bool = Field(
        default=False,
        description="Set to true to confirm large adjustments (>50%)",
    )
    
    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return v.upper().strip()
    
    @field_validator("reason")
    @classmethod
    def validate_adjustment_reason(cls, v: MovementReason) -> MovementReason:
        """Only allow valid adjustment reasons."""
        valid_reasons = {
            MovementReason.CYCLE_COUNT,
            MovementReason.AUDIT_CORRECTION,
            MovementReason.SYSTEM_CORRECTION,
            MovementReason.SHRINKAGE,
        }
        if v not in valid_reasons:
            raise ValueError(
                f"Invalid adjustment reason. Must be one of: "
                f"{', '.join(r.value for r in valid_reasons)}"
            )
        return v


class ReserveStockRequest(StrictModel):
    """
    Request to reserve stock for an online order.
    
    Used by: System (automated), staff
    Endpoint: POST /inventory/reserve
    """
    
    sku: str = Field(..., min_length=1, max_length=50)
    location_id: str = Field(..., min_length=1)
    
    quantity: int = Field(
        ...,
        gt=0,
        le=100,  # Reasonable limit for single order
        description="Units to reserve",
    )
    
    order_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Order reference ID",
    )
    
    notes: str | None = Field(default=None, max_length=500)
    
    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return v.upper().strip()


class ReleaseReservationRequest(StrictModel):
    """
    Request to release a stock reservation.
    
    Used by: System (automated), staff, managers
    Endpoint: POST /inventory/release
    """
    
    sku: str = Field(..., min_length=1, max_length=50)
    location_id: str = Field(..., min_length=1)
    
    quantity: int = Field(
        ...,
        gt=0,
        description="Units to release",
    )
    
    order_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Original order reference",
    )
    
    notes: str | None = Field(default=None, max_length=500)
    
    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return v.upper().strip()


class FulfillOrderRequest(StrictModel):
    """
    Request to fulfill an order (sell stock).
    
    Used by: Cashiers, staff
    Endpoint: POST /inventory/fulfill
    """
    
    sku: str = Field(..., min_length=1, max_length=50)
    location_id: str = Field(..., min_length=1)
    
    quantity: int = Field(
        ...,
        gt=0,
        le=1000,
        description="Units sold",
    )
    
    order_id: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Order/transaction ID",
    )
    
    notes: str | None = Field(default=None, max_length=500)
    
    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return v.upper().strip()


class DisposeStockRequest(StrictModel):
    """
    Request to dispose of stock (expired/damaged).
    
    Used by: Managers only
    Endpoint: POST /inventory/dispose
    """
    
    sku: str = Field(..., min_length=1, max_length=50)
    location_id: str = Field(..., min_length=1)
    
    quantity: int = Field(
        ...,
        gt=0,
        le=10000,
        description="Units to dispose",
    )
    
    reason: MovementReason = Field(
        ...,
        description="Disposal reason",
    )
    
    batch_id: str | None = Field(
        default=None,
        description="Specific batch being disposed",
    )
    
    notes: str = Field(
        ...,
        min_length=10,
        max_length=500,
        description="Explanation for disposal (required)",
    )
    
    @field_validator("sku")
    @classmethod
    def validate_sku(cls, v: str) -> str:
        return v.upper().strip()
    
    @field_validator("reason")
    @classmethod
    def validate_disposal_reason(cls, v: MovementReason) -> MovementReason:
        """Only allow valid disposal reasons."""
        valid_reasons = {
            MovementReason.EXPIRED,
            MovementReason.DAMAGED,
            MovementReason.SHRINKAGE,
        }
        if v not in valid_reasons:
            raise ValueError(
                f"Invalid disposal reason. Must be one of: "
                f"{', '.join(r.value for r in valid_reasons)}"
            )
        return v


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════

class ProductSummary(BaseModel):
    """Embedded product info in responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    sku: str
    name: str
    category: str
    is_perishable: bool


class LocationSummary(BaseModel):
    """Embedded location info in responses."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    code: str
    name: str
    location_type: LocationType


class InventoryItemResponse(BaseModel):
    """
    Full inventory item response.
    
    Includes computed online_available field.
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    product_id: str
    location_id: str
    physical_stock: int
    buffer: int
    reorder_point: int
    max_stock: int | None
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    # Nested objects (when loaded)
    product: ProductSummary | None = None
    location: LocationSummary | None = None
    
    @computed_field
    @property
    def online_available(self) -> int:
        """Derived field: max(physical_stock - buffer, 0)."""
        return max(self.physical_stock - self.buffer, 0)
    
    @computed_field
    @property
    def is_low_stock(self) -> bool:
        """Is stock at or below reorder point?"""
        return self.physical_stock <= self.reorder_point
    
    @computed_field
    @property
    def is_out_of_stock(self) -> bool:
        """Is stock zero?"""
        return self.physical_stock == 0


class StockMovementResponse(BaseModel):
    """Stock movement audit record response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    inventory_item_id: str
    movement_type: MovementType
    reason: MovementReason | None
    quantity_delta: int
    quantity_before: int
    quantity_after: int
    user_id: str
    reference_id: str | None
    reference_type: str | None
    notes: str | None
    created_at: datetime


class StockOperationResponse(BaseModel):
    """
    Response for stock operations.
    
    Returned by: receive, adjust, reserve, release, fulfill, dispose
    """
    
    success: bool = True
    message: str
    
    item: InventoryItemResponse
    movement: StockMovementResponse
    
    previous_stock: int
    new_stock: int
    
    @computed_field
    @property
    def delta(self) -> int:
        """Stock change amount."""
        return self.new_stock - self.previous_stock


class StockLevelResponse(BaseModel):
    """Response for stock level queries."""
    
    sku: str
    location_id: str | None
    physical_stock: int
    buffer: int
    online_available: int
    is_low_stock: bool | None = None
    reorder_point: int | None = None


class LowStockAlertResponse(BaseModel):
    """Low stock alert item."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    sku: str
    product_name: str
    location_code: str
    physical_stock: int
    reorder_point: int
    shortage: int  # How many units below reorder point
    
    @classmethod
    def from_inventory_item(cls, item) -> "LowStockAlertResponse":
        """Create from InventoryItem model."""
        return cls(
            id=item.id,
            sku=item.product.sku,
            product_name=item.product.name,
            location_code=item.location.code,
            physical_stock=item.physical_stock,
            reorder_point=item.reorder_point,
            shortage=item.reorder_point - item.physical_stock,
        )


class ExpiringBatchResponse(BaseModel):
    """Expiring batch alert."""
    
    model_config = ConfigDict(from_attributes=True)
    
    batch_id: str
    sku: str
    product_name: str
    location_code: str
    quantity: int
    expiry_date: datetime
    days_until_expiry: int
    batch_number: str | None


class MovementHistoryResponse(BaseModel):
    """Paginated movement history."""
    
    sku: str
    location_id: str
    movements: list[StockMovementResponse]
    total: int


class InventorySummaryResponse(BaseModel):
    total_products: int
    low_stock: int
    out_of_stock: int
    below_threshold: int
    last_sync_at: datetime | None


class InventoryListItemResponse(BaseModel):
    sku: str
    name: str
    category: str
    category_id: str
    variant: str | None
    stock: int
    threshold: int
    price: Decimal
    gst: Decimal
    status: str
    last_updated: datetime | None


class InventoryListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[InventoryListItemResponse]


class UpdateStockRequest(StrictModel):
    stock: int = Field(..., ge=0)
    location_id: str | None = Field(default=None)


class UpdateStockResponse(BaseModel):
    sku: str
    stock: int
    status: str
    last_updated: datetime | None


class UpdateThresholdRequest(StrictModel):
    threshold: int = Field(..., ge=0)
    location_id: str | None = Field(default=None)


class UpdateThresholdResponse(BaseModel):
    sku: str
    threshold: int


class InventoryHistoryItemResponse(BaseModel):
    type: str
    change: int
    stock: int
    at: datetime
    user: str | None = None
    source: str | None = None


class InventoryHistoryResponse(BaseModel):
    items: list[InventoryHistoryItemResponse]
    total: int


class RestockPriorityItemResponse(BaseModel):
    sku: str
    name: str
    stock: int
    threshold: int
    supplier: str | None = None


class RestockPriorityResponse(BaseModel):
    items: list[RestockPriorityItemResponse]


class ExpiryWatchItemResponse(BaseModel):
    sku: str
    name: str
    days_to_expire: int
    batch: str | None = None


class ExpiryWatchResponse(BaseModel):
    items: list[ExpiryWatchItemResponse]


class InventoryImportResponse(BaseModel):
    updated: int
    low_stock_alerts: int
    skipped: int


# ═══════════════════════════════════════════════════════════════════════════
# QUERY PARAMETERS
# ═══════════════════════════════════════════════════════════════════════════

class PaginationParams(BaseModel):
    """Pagination query parameters."""
    
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class StockQueryParams(BaseModel):
    """Parameters for stock queries."""
    
    sku: str | None = None
    location_id: str | None = None
    low_stock_only: bool = False
    out_of_stock_only: bool = False
