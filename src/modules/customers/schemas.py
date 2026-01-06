"""
Customers Schemas
-----------------
Pydantic models for customer endpoints.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


CustomerStatus = Literal["new", "active", "at_risk", "inactive"]
CustomerSegment = Literal["VIP", "Wholesale", "Local", "Online", "Lapsed"]
SortBy = Literal["name", "lifetime_value", "last_order_at", "orders_count", "created_at"]
SortDir = Literal["asc", "desc"]
InviteStatus = Literal["not_sent", "sent", "accepted"]

ActionStatus = Literal["open", "done", "snoozed"]
ActionPriority = Literal["low", "medium", "high"]

ContactChannel = Literal["phone", "sms", "email"]


class CustomerOwner(StrictModel):
    id: str
    name: str


class CustomerListItem(StrictModel):
    id: str
    name: str
    email: str | None
    phone: str | None
    status: CustomerStatus
    segment: CustomerSegment
    location: str | None
    owner: CustomerOwner | None
    lifetime_value: float
    orders_count: int
    avg_order_value: float
    last_order_at: datetime | None
    last_contact_at: datetime | None
    next_action: str | None
    loyalty_tier: str | None
    tags: list[str]
    risk_score: int
    invite_status: InviteStatus | None = None


class CustomerMeta(StrictModel):
    active_count: int
    at_risk_count: int


class CustomersListResponse(StrictModel):
    items: list[CustomerListItem]
    total: int
    meta: CustomerMeta | None = None


class CustomersSummaryResponse(StrictModel):
    total_customers: int
    active_customers: int
    at_risk_customers: int
    average_order_value: float
    ltv_total: float
    retention_rate: float


class CustomerSpotlight(StrictModel):
    id: str
    name: str
    segment: CustomerSegment
    loyalty_tier: str | None
    lifetime_value: float
    notes: str | None


class CustomersSpotlightResponse(StrictModel):
    customer: CustomerSpotlight
    goal_ltv: float
    progress_pct: int


class CustomerActionItem(StrictModel):
    id: str
    customer_id: str
    customer_name: str
    title: str
    due_at: datetime
    priority: ActionPriority
    status: ActionStatus
    last_order_at: datetime | None


class CustomersActionsResponse(StrictModel):
    items: list[CustomerActionItem]
    total: int


class ExperienceMetric(StrictModel):
    key: str
    label: str
    value: int


class CustomersExperienceResponse(StrictModel):
    metrics: list[ExperienceMetric]


class SegmentFocusItem(StrictModel):
    segment: CustomerSegment
    count: int
    focus: str


class CustomersSegmentsResponse(StrictModel):
    items: list[SegmentFocusItem]


class OpportunityItem(StrictModel):
    label: str
    count: int
    progress_pct: int


class ImpactItem(StrictModel):
    label: str
    value: float | str


class CustomersOpportunitiesResponse(StrictModel):
    upsell: list[OpportunityItem]
    impact: list[ImpactItem]


class CustomerDetailResponse(CustomerListItem):
    notes: str | None = None


class CustomerContactRequest(StrictModel):
    channel: ContactChannel
    note: str | None = Field(default=None, max_length=500)


class CustomerContactResponse(StrictModel):
    ok: bool
    channel: ContactChannel
    noted_at: datetime


class CustomerInviteRequest(StrictModel):
    send: bool = True
    note: str | None = Field(default=None, max_length=500)


class CustomerCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    segment: CustomerSegment
    status: CustomerStatus = "new"
    owner_id: str | None = None
    next_action: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    tags: list[str] = Field(default_factory=list)
    invite: CustomerInviteRequest | None = None


class CustomerCreateResponse(CustomerDetailResponse):
    invite_status: InviteStatus


class CustomerInviteSendRequest(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class CustomerInviteSendResponse(StrictModel):
    status: InviteStatus
    sent_at: datetime


class CustomerInviteStatusResponse(StrictModel):
    status: InviteStatus
    sent_at: datetime | None
    accepted_at: datetime | None


class CustomerInviteAcceptRequest(StrictModel):
    token: str
    password: str
    password_confirm: str


class CustomerInviteAcceptResponse(StrictModel):
    message: str
    customer_id: str


class CustomerInviteVerifyResponse(StrictModel):
    valid: bool
    expires_at: datetime | None
    customer_email: str | None
