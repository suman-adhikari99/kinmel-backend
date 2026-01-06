"""
Customers Router
----------------
Frontend-only UX endpoints for customers dashboard.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from src.api.deps import CurrentUser, DbSession
from src.modules.customers.repository import customers_repository
from src.modules.customers.schemas import (
    ActionStatus,
    CustomerCreateRequest,
    CustomerCreateResponse,
    CustomerContactRequest,
    CustomerContactResponse,
    CustomerDetailResponse,
    CustomerInviteAcceptRequest,
    CustomerInviteAcceptResponse,
    CustomerInviteSendRequest,
    CustomerInviteSendResponse,
    CustomerInviteStatusResponse,
    CustomerInviteVerifyResponse,
    CustomerSegment,
    CustomerStatus,
    CustomersActionsResponse,
    CustomersExperienceResponse,
    CustomersListResponse,
    CustomersOpportunitiesResponse,
    CustomersSegmentsResponse,
    CustomersSpotlightResponse,
    CustomersSummaryResponse,
    SortBy,
    SortDir,
)


router = APIRouter(
    prefix="/customers",
    tags=["Customers"],
    responses={401: {"description": "Not authenticated"}},
)


@router.get(
    "",
    response_model=CustomersListResponse,
    summary="List customers",
)
async def list_customers(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None),
    status_filter: CustomerStatus | None = Query(None, alias="status"),
    segment: CustomerSegment | None = Query(None),
    owner_id: str | None = Query(None),
    min_ltv: float | None = Query(None, ge=0),
    max_ltv: float | None = Query(None, ge=0),
    last_order_before: date | None = Query(None),
    last_order_after: date | None = Query(None),
    sort_by: SortBy = Query("created_at"),
    sort_dir: SortDir = Query("desc"),
) -> CustomersListResponse:
    items, total, meta_counts = await customers_repository.list_customers(
        db,
        limit=limit,
        offset=offset,
        search=search,
        status=status_filter,
        segment=segment,
        owner_id=owner_id,
        min_ltv=min_ltv,
        max_ltv=max_ltv,
        last_order_before=last_order_before,
        last_order_after=last_order_after,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return CustomersListResponse(
        items=items,
        total=total,
        meta={"active_count": meta_counts["active"], "at_risk_count": meta_counts["at_risk"]},
    )


@router.post(
    "",
    response_model=CustomerCreateResponse,
    summary="Create customer and optionally send invite",
)
async def create_customer(
    payload: CustomerCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> CustomerCreateResponse:
    invite_send = payload.invite.send if payload.invite else False
    invite_note = payload.invite.note if payload.invite else None
    customer = await customers_repository.create_customer(
        db,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        location=payload.location,
        segment=payload.segment,
        status=payload.status,
        owner_id=payload.owner_id,
        next_action=payload.next_action,
        notes=payload.notes,
        tags=payload.tags,
        invite_send=invite_send,
        invite_note=invite_note,
    )
    return CustomerCreateResponse(**customer)


@router.get(
    "/summary",
    response_model=CustomersSummaryResponse,
    summary="Customer summary",
)
async def customer_summary(
    user: CurrentUser,
    db: DbSession,
) -> CustomersSummaryResponse:
    summary = await customers_repository.get_summary(db)
    return CustomersSummaryResponse(**summary)


@router.get(
    "/spotlight",
    response_model=CustomersSpotlightResponse,
    summary="Customer spotlight",
)
async def customer_spotlight(
    user: CurrentUser,
    db: DbSession,
) -> CustomersSpotlightResponse:
    spotlight = await customers_repository.get_spotlight(db)
    return CustomersSpotlightResponse(**spotlight)


@router.get(
    "/actions",
    response_model=CustomersActionsResponse,
    summary="Customer action queue",
)
async def customer_actions(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    owner_id: str | None = Query(None),
    status_filter: ActionStatus | None = Query(None, alias="status"),
) -> CustomersActionsResponse:
    items, total = await customers_repository.list_actions(
        db,
        limit=limit,
        offset=offset,
        owner_id=owner_id,
        status=status_filter,
    )
    return CustomersActionsResponse(items=items, total=total)


@router.get(
    "/experience",
    response_model=CustomersExperienceResponse,
    summary="Customer experience metrics",
)
async def customer_experience(
    user: CurrentUser,
    db: DbSession,
) -> CustomersExperienceResponse:
    metrics = await customers_repository.get_experience(db)
    return CustomersExperienceResponse(**metrics)


@router.get(
    "/segments",
    response_model=CustomersSegmentsResponse,
    summary="Customer segments focus",
)
async def customer_segments(
    user: CurrentUser,
    db: DbSession,
) -> CustomersSegmentsResponse:
    segments = await customers_repository.get_segments(db)
    return CustomersSegmentsResponse(**segments)


@router.get(
    "/opportunities",
    response_model=CustomersOpportunitiesResponse,
    summary="Customer opportunities",
)
async def customer_opportunities(
    user: CurrentUser,
    db: DbSession,
) -> CustomersOpportunitiesResponse:
    opportunities = await customers_repository.get_opportunities(db)
    return CustomersOpportunitiesResponse(**opportunities)


@router.get(
    "/invite/verify",
    response_model=CustomerInviteVerifyResponse,
    summary="Verify invite token",
)
async def verify_invite(
    db: DbSession,
    token: str = Query(...),
) -> CustomerInviteVerifyResponse:
    result = await customers_repository.verify_invite_token(db, token)
    return CustomerInviteVerifyResponse(**result)


@router.post(
    "/invite/accept",
    response_model=CustomerInviteAcceptResponse,
    summary="Accept customer invite",
)
async def accept_invite(
    payload: CustomerInviteAcceptRequest,
    db: DbSession,
) -> CustomerInviteAcceptResponse:
    if payload.password != payload.password_confirm:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Passwords do not match")
    result = await customers_repository.accept_invite(db, token=payload.token)
    if not result:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired token")
    return CustomerInviteAcceptResponse(**result)


@router.get(
    "/{customer_id}",
    response_model=CustomerDetailResponse,
    summary="Customer detail",
)
async def customer_detail(
    customer_id: str,
    user: CurrentUser,
    db: DbSession,
) -> CustomerDetailResponse:
    customer = await customers_repository.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerDetailResponse(**customer)


@router.post(
    "/{customer_id}/invite",
    response_model=CustomerInviteSendResponse,
    summary="Send customer invite",
)
async def send_invite(
    customer_id: str,
    payload: CustomerInviteSendRequest,
    user: CurrentUser,
    db: DbSession,
) -> CustomerInviteSendResponse:
    result = await customers_repository.send_invite(
        db,
        customer_id=customer_id,
        note=payload.note,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerInviteSendResponse(**result)


@router.get(
    "/{customer_id}/invite",
    response_model=CustomerInviteStatusResponse,
    summary="Get invite status",
)
async def invite_status(
    customer_id: str,
    user: CurrentUser,
    db: DbSession,
) -> CustomerInviteStatusResponse:
    result = await customers_repository.get_invite_status(db, customer_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerInviteStatusResponse(**result)


@router.post(
    "/{customer_id}/contact",
    response_model=CustomerContactResponse,
    summary="Log customer contact",
)
async def customer_contact(
    customer_id: str,
    payload: CustomerContactRequest,
    user: CurrentUser,
    db: DbSession,
) -> CustomerContactResponse:
    result = await customers_repository.log_contact(
        db,
        customer_id=customer_id,
        channel=payload.channel,
        note=payload.note,
    )
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerContactResponse(**result)
