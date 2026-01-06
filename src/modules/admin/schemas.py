"""
Admin API Schemas
-----------------
Pydantic v2 models for admin/audit endpoints.

Design Principles:
1. Never expose internal IDs (UUIDs) - use business identifiers
2. Never expose PII (personally identifiable information)
3. Strict enum validation for action types
4. ISO 8601 date format with timezone awareness
5. Clear pagination with total counts
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS (Strict validation)
# ═══════════════════════════════════════════════════════════════════════════


class AuditActionType(StrEnum):
    """
    Allowed action types for audit log queries.
    
    Maps to MovementType in inventory models, but exposed
    with user-friendly names for the API.
    """
    
    RECEIVING = "receiving"      # Stock received from suppliers
    SALE = "sale"               # Stock sold to customers
    TRANSFER = "transfer"       # Stock moved between locations
    ADJUSTMENT = "adjustment"   # Manual stock corrections
    RETURN = "return"          # Customer returns
    DISPOSAL = "disposal"      # Expired/damaged removal
    RESERVATION = "reservation" # Reserved for online orders
    
    @classmethod
    def all_values(cls) -> list[str]:
        return [item.value for item in cls]


class AuditReasonType(StrEnum):
    """Standardized reasons for audit filtering."""
    
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


# ═══════════════════════════════════════════════════════════════════════════
# QUERY SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════


class AuditLogQueryParams(BaseModel):
    """
    Query parameters for audit log endpoint.
    
    All filters are optional and combined with AND logic.
    
    Example:
        GET /admin/audit-log?sku=MILK-2L&action_type=sale&start_date=2024-01-01
    """
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Entity Filters
    # ─────────────────────────────────────────────────────────────────
    
    sku: str | None = Field(
        default=None,
        max_length=50,
        description="Filter by product SKU (case-insensitive)",
        examples=["MILK-2L-WHOLE", "BREAD-WHITE"],
    )
    
    location_code: str | None = Field(
        default=None,
        max_length=50,
        description="Filter by location code (e.g., 'FLOOR-A1', 'COLD-01')",
        examples=["FLOOR-A1", "COLD-01"],
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Action Filters
    # ─────────────────────────────────────────────────────────────────
    
    action_type: AuditActionType | None = Field(
        default=None,
        description=f"Filter by action type. Options: {', '.join(AuditActionType.all_values())}",
    )
    
    reason: AuditReasonType | None = Field(
        default=None,
        description="Filter by specific reason code",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # User Filter (by display name, not ID)
    # ─────────────────────────────────────────────────────────────────
    
    performed_by: str | None = Field(
        default=None,
        max_length=100,
        description="Filter by user who performed the action (partial match)",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Date Range Filters
    # ─────────────────────────────────────────────────────────────────
    
    start_date: datetime | None = Field(
        default=None,
        description="Filter records from this date/time (ISO 8601 format)",
        examples=["2024-01-01T00:00:00Z", "2024-01-15"],
    )
    
    end_date: datetime | None = Field(
        default=None,
        description="Filter records until this date/time (ISO 8601 format)",
        examples=["2024-01-31T23:59:59Z", "2024-01-31"],
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Reference Filters
    # ─────────────────────────────────────────────────────────────────
    
    reference_id: str | None = Field(
        default=None,
        max_length=50,
        description="Filter by reference ID (order ID, PO number, etc.)",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Pagination
    # ─────────────────────────────────────────────────────────────────
    
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum records to return (default: 50, max: 500)",
    )
    
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of records to skip (for pagination)",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Validators
    # ─────────────────────────────────────────────────────────────────
    
    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, v: str | None) -> str | None:
        """Normalize SKU to uppercase."""
        if v:
            return v.upper().strip()
        return v
    
    @field_validator("location_code")
    @classmethod
    def normalize_location(cls, v: str | None) -> str | None:
        """Normalize location code to uppercase."""
        if v:
            return v.upper().strip()
        return v
    
    @model_validator(mode="after")
    def validate_date_range(self) -> "AuditLogQueryParams":
        """Ensure start_date is before end_date."""
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be before end_date")
        return self


# ═══════════════════════════════════════════════════════════════════════════
# RESPONSE SCHEMAS
# ═══════════════════════════════════════════════════════════════════════════


class AuditLogEntry(BaseModel):
    """
    Single audit log entry in response.
    
    ⚠️ PRIVACY: This schema intentionally omits:
    - Internal UUIDs (uses business identifiers instead)
    - User email/PII (shows display name only)
    - Raw database fields
    """
    
    model_config = ConfigDict(from_attributes=True)
    
    # ─────────────────────────────────────────────────────────────────
    # What changed
    # ─────────────────────────────────────────────────────────────────
    
    sku: str = Field(
        description="Product SKU that was affected",
        examples=["MILK-2L-WHOLE"],
    )
    
    product_name: str = Field(
        description="Product display name",
        examples=["Whole Milk 2L"],
    )
    
    location_code: str = Field(
        description="Location code where change occurred",
        examples=["FLOOR-A1"],
    )
    
    location_name: str = Field(
        description="Location display name",
        examples=["Aisle 1 Floor Shelves"],
    )
    
    # ─────────────────────────────────────────────────────────────────
    # The change
    # ─────────────────────────────────────────────────────────────────
    
    action_type: AuditActionType = Field(
        description="Type of action performed",
    )
    
    reason: str | None = Field(
        description="Reason code for the action",
        examples=["cycle_count", "customer_sale"],
    )
    
    quantity_delta: int = Field(
        description="Change in quantity (+increase, -decrease)",
        examples=[10, -5, 0],
    )
    
    quantity_before: int = Field(
        description="Stock level before this action",
    )
    
    quantity_after: int = Field(
        description="Stock level after this action",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Who and when
    # ─────────────────────────────────────────────────────────────────
    
    performed_by: str = Field(
        description="Name of user who performed action (not email/ID)",
        examples=["John Smith"],
    )
    
    timestamp: datetime = Field(
        description="When the action occurred (ISO 8601 with timezone)",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Context
    # ─────────────────────────────────────────────────────────────────
    
    reference_id: str | None = Field(
        default=None,
        description="Related reference (order ID, PO number, etc.)",
        examples=["ORD-2024-001", "PO-12345"],
    )
    
    reference_type: str | None = Field(
        default=None,
        description="Type of reference",
        examples=["order", "purchase_order", "transfer"],
    )
    
    notes: str | None = Field(
        default=None,
        description="Staff notes explaining the action",
    )
    
    # ─────────────────────────────────────────────────────────────────
    # Computed fields
    # ─────────────────────────────────────────────────────────────────
    
    @computed_field
    @property
    def change_direction(self) -> str:
        """Human-readable change direction."""
        if self.quantity_delta > 0:
            return "increase"
        elif self.quantity_delta < 0:
            return "decrease"
        return "no_change"


class AuditLogResponse(BaseModel):
    """
    Paginated audit log response.
    
    Includes:
    - List of audit entries
    - Pagination metadata
    - Applied filters (for debugging)
    """
    
    entries: list[AuditLogEntry] = Field(
        description="List of audit log entries",
    )
    
    total: int = Field(
        description="Total matching records (before pagination)",
    )
    
    limit: int = Field(
        description="Maximum records requested",
    )
    
    offset: int = Field(
        description="Records skipped",
    )
    
    filters_applied: dict[str, Any] = Field(
        default_factory=dict,
        description="Filters that were applied to this query",
    )
    
    @computed_field
    @property
    def has_more(self) -> bool:
        """Are there more records beyond this page?"""
        return (self.offset + len(self.entries)) < self.total
    
    @computed_field
    @property
    def page(self) -> int:
        """Current page number (1-indexed)."""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1
    
    @computed_field
    @property
    def total_pages(self) -> int:
        """Total number of pages."""
        if self.limit == 0:
            return 1
        return (self.total + self.limit - 1) // self.limit


# ═══════════════════════════════════════════════════════════════════════════
# STATS RESPONSE
# ═══════════════════════════════════════════════════════════════════════════


class ActionTypeStats(BaseModel):
    """Stats for a single action type."""
    
    action_type: AuditActionType
    count: int
    total_units_affected: int
    
    @computed_field
    @property
    def average_units_per_action(self) -> float:
        """Average units affected per action."""
        if self.count == 0:
            return 0.0
        return round(self.total_units_affected / self.count, 2)


class DailyActivityStats(BaseModel):
    """Daily activity breakdown."""
    
    date: str = Field(description="Date in YYYY-MM-DD format")
    total_actions: int
    total_units_increased: int
    total_units_decreased: int
    
    @computed_field
    @property
    def net_change(self) -> int:
        """Net stock change for the day."""
        return self.total_units_increased - self.total_units_decreased


class AuditStatsResponse(BaseModel):
    """
    Aggregated audit statistics.
    
    Provides summary metrics for dashboards and reporting.
    """
    
    period_start: datetime = Field(
        description="Start of statistics period",
    )
    
    period_end: datetime = Field(
        description="End of statistics period",
    )
    
    total_actions: int = Field(
        description="Total number of stock movements",
    )
    
    total_units_increased: int = Field(
        description="Total units added to inventory",
    )
    
    total_units_decreased: int = Field(
        description="Total units removed from inventory",
    )
    
    by_action_type: list[ActionTypeStats] = Field(
        description="Breakdown by action type",
    )
    
    by_day: list[DailyActivityStats] = Field(
        description="Daily activity breakdown",
    )
    
    top_products: list[dict[str, Any]] = Field(
        description="Most active products (by movement count)",
    )
    
    top_users: list[dict[str, Any]] = Field(
        description="Most active users (by movement count)",
    )
    
    @computed_field
    @property
    def net_stock_change(self) -> int:
        """Net change in total stock during period."""
        return self.total_units_increased - self.total_units_decreased


# ═══════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════════════════


class CSVExportParams(AuditLogQueryParams):
    """
    Parameters for CSV export.
    
    Inherits all filters from AuditLogQueryParams but overrides
    pagination limits for bulk export.
    """
    
    limit: int = Field(
        default=10000,
        ge=1,
        le=100000,
        description="Maximum records to export (default: 10,000, max: 100,000)",
    )
    
    offset: int = Field(
        default=0,
        ge=0,
        description="Records to skip",
    )
