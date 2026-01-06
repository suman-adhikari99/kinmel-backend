"""
Order API Schemas
-----------------
Pydantic v2 models for order request/response validation.
"""

from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, computed_field

from src.modules.orders.models import (
    ContactChannel,
    OrderStatus,
    OrderType,
    SubstitutionStatus,
)


# ═══════════════════════════════════════════════════════════════════
# BASE SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class StrictModel(BaseModel):
    """Base model with strict configuration."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )


# ═══════════════════════════════════════════════════════════════════
# SHARED COMPONENTS
# ═══════════════════════════════════════════════════════════════════

class OrderCustomer(StrictModel):
    """Customer information displayed in UI."""

    name: str
    phone: str
    email: str | None = None


class OrderTimestamps(StrictModel):
    """Timestamp bundle for UI display."""

    updated_at: datetime
    delivered_at: datetime | None = None


class OrderItemSubstitute(StrictModel):
    """Substitute item details."""

    id: str | None = None
    name: str
    price: Decimal


class OrderItemSubstitutionResponse(StrictModel):
    """Substitution details shown per item."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    original_item_id: str | None = None
    original_name: str
    original_price: Decimal
    original_qty: Decimal
    reason: str
    price_difference: Decimal | None = None
    customer_notified: bool | None = None
    status: SubstitutionStatus
    substitute_item_id: str | None = Field(default=None, exclude=True)
    substitute_name: str = Field(exclude=True)
    substitute_price: Decimal = Field(exclude=True)
    quantity: Decimal

    @computed_field
    @property
    def substitute(self) -> OrderItemSubstitute:
        return OrderItemSubstitute(
            id=self.substitute_item_id,
            name=self.substitute_name,
            price=self.substitute_price,
        )


class OrderItemResponse(StrictModel):
    """Order item response for list/detail views."""

    id: str
    name: str
    quantity: Decimal
    price: Decimal
    checked: bool | None = None
    substitution: OrderItemSubstitutionResponse | None = None


class OrderStatusHistoryResponse(StrictModel):
    """Order status history entry."""

    status: OrderStatus
    at: datetime = Field(..., validation_alias="created_at")
    by: str | None = Field(default=None, validation_alias="changed_by")


class OrderContactAttemptResponse(StrictModel):
    """Order contact attempt response."""

    channel: ContactChannel
    template_id: str | None = None
    notes: str | None = None
    created_at: datetime


# ═══════════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class UpdateOrderStatusRequest(StrictModel):
    """Request to update order status."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    status: OrderStatus


class UpdateOrderItemChecklistRequest(StrictModel):
    """Request to update item checklist state."""

    checked: bool


class CreateSubstitutionRequest(StrictModel):
    """Request to create or update an item substitution."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    original_item_id: str = Field(..., min_length=1)
    substitute_item_id: str = Field(..., min_length=1)
    quantity: Decimal = Field(..., gt=0)
    reason: str
    status: SubstitutionStatus
    price_difference: Decimal | None = None
    customer_notified: bool | None = None


class LogContactAttemptRequest(StrictModel):
    """Request to log a contact attempt."""

    channel: ContactChannel
    template_id: str | None = None
    notes: str | None = None


# ═══════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════

class OrderSummaryResponse(StrictModel):
    """Order summary for list view."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    id: str
    order_type: OrderType = Field(..., serialization_alias="type")
    status: OrderStatus
    created_at: datetime
    time_slot: str | None = None

    customer_name: str = Field(exclude=True)
    customer_phone: str = Field(exclude=True)
    customer_email: str | None = Field(default=None, exclude=True)

    delivery_address: str | None = Field(default=None, exclude=True)
    delivery_suburb: str | None = Field(default=None, exclude=True)

    items: list[OrderItemResponse]

    subtotal: Decimal
    gst: Decimal
    delivery_fee: Decimal
    total: Decimal
    notes: str | None = None
    has_substitutions: bool

    updated_at: datetime = Field(exclude=True)
    delivered_at: datetime | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def customer(self) -> OrderCustomer:
        return OrderCustomer(
            name=self.customer_name,
            phone=self.customer_phone,
            email=self.customer_email,
        )

    @computed_field
    @property
    def address(self) -> str | None:
        return self.delivery_address or self.delivery_suburb

    @computed_field
    @property
    def suburb(self) -> str | None:
        return self.delivery_suburb

    @computed_field
    @property
    def timestamps(self) -> OrderTimestamps:
        return OrderTimestamps(
            updated_at=self.updated_at,
            delivered_at=self.delivered_at,
        )


class OrderDetailResponse(OrderSummaryResponse):
    """Order detail response with status history."""

    status_history: list[OrderStatusHistoryResponse] | None = None


class OrderListResponse(StrictModel):
    """Paginated order list response."""

    items: list[OrderSummaryResponse] = Field(
        default_factory=list,
        validation_alias="orders",
    )
    total: int
    limit: int
    offset: int

    @computed_field
    @property
    def has_more(self) -> bool:
        return (self.offset + len(self.items)) < self.total

    @computed_field
    @property
    def page(self) -> int:
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1

    @computed_field
    @property
    def total_pages(self) -> int:
        if self.limit == 0:
            return 1
        return (self.total + self.limit - 1) // self.limit


class OrderOperationResponse(StrictModel):
    """Standard response for order updates."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    order_id: str
    status: OrderStatus
    timestamp: datetime
    order: OrderDetailResponse


class OrderItemUpdateResponse(StrictModel):
    """Response for item checklist updates."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    order_id: str
    status: OrderStatus
    timestamp: datetime
    item: OrderItemResponse
    order: OrderDetailResponse


class OrderContactResponse(StrictModel):
    """Response for logged contact attempts."""

    order_id: str
    status: OrderStatus
    timestamp: datetime
    contact: OrderContactAttemptResponse
    order: OrderDetailResponse


class OrderStatusSummaryResponse(StrictModel):
    """Order status summary counts."""

    total: int
    pending: int
    preparing: int
    ready: int
    out_for_delivery: int
    completed: int
    cancelled: int


class OrderExportEmailResponse(StrictModel):
    """Response for queued order export email."""

    status: str
    message: str
    task_id: str


class OrderExportRequest(StrictModel):
    """Request to start an export job."""

    model_config = ConfigDict(
        strict=False,
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        from_attributes=True,
        populate_by_name=True,
    )

    status: str | None = None
    order_type: OrderType | None = Field(default=None, alias="type")
    start_date: datetime | None = None
    end_date: datetime | None = None
    search: str | None = None
    destination_email: str | None = None


class OrderExportJobResponse(StrictModel):
    """Export job status response."""

    job_id: str
    status: str
    destination_email: str
    requested_at: datetime
    file_url: str | None = None
    error_message: str | None = None
