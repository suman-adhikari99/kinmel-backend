"""
Order API Router
----------------
REST endpoints for order management and fulfillment.
"""

import csv
import io
from datetime import UTC, datetime
from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from starlette.responses import StreamingResponse

from src.api.deps import CurrentUser, DbSession, RequireStaff
from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import get_logger
from src.modules.orders.models import OrderStatus, OrderType
from src.modules.orders.schemas import (
    CreateSubstitutionRequest,
    LogContactAttemptRequest,
    OrderContactAttemptResponse,
    OrderContactResponse,
    OrderDetailResponse,
    OrderExportJobResponse,
    OrderExportRequest,
    OrderItemResponse,
    OrderItemUpdateResponse,
    OrderExportEmailResponse,
    OrderListResponse,
    OrderOperationResponse,
    OrderSummaryResponse,
    OrderStatusSummaryResponse,
    UpdateOrderItemChecklistRequest,
    UpdateOrderStatusRequest,
)
from src.modules.orders.service import (
    OrderListFilters,
    SubstitutionInput,
    order_service,
)
from src.modules.users.models import User
from src.tasks.order_tasks import export_orders_email

logger = get_logger(__name__)

router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Resource not found"},
        422: {"description": "Validation error"},
    },
)


# ═══════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════


def handle_service_error(e: Exception) -> None:
    """Convert service exceptions to HTTP exceptions."""
    if isinstance(e, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": e.staff_message,
                "code": "NOT_FOUND",
                "resource": e.details.get("resource"),
                "identifier": e.details.get("identifier"),
            },
        )
    if isinstance(e, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.staff_message,
                "code": "VALIDATION_ERROR",
                "field": e.details.get("field"),
            },
        )
    logger.exception("Unexpected error in orders module")
    raise


def parse_status_filter(status_value: str | None) -> OrderStatus | None:
    """Normalize status filters with alias support."""
    if not status_value:
        return None
    normalized_status = status_value.strip().lower()
    if normalized_status in {"pending", "created"}:
        return OrderStatus.NEW
    try:
        return OrderStatus(normalized_status)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Invalid status value",
                "code": "INVALID_STATUS",
                "allowed": [status.value for status in OrderStatus],
            },
        ) from exc


def parse_ordering(value: str | None) -> tuple[str, bool]:
    """Parse ordering into field and descending flag."""
    if not value:
        return "created_at", True
    descending = value.startswith("-")
    field = value[1:] if descending else value
    if field not in {"created_at"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Invalid ordering value",
                "code": "INVALID_ORDERING",
                "allowed": ["created_at", "-created_at"],
            },
        )
    return field, descending


async def get_user_email(db: DbSession, user_id: str) -> str:
    """Fetch user's email from DB."""
    result = await db.execute(
        select(User.email).where(User.id == user_id, User.deleted_at.is_(None))
    )
    email = result.scalar_one_or_none()
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return email


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Normalize datetimes to UTC; assume naive values are UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def normalize_date_range(
    start_date: datetime | None,
    end_date: datetime | None,
) -> tuple[datetime | None, datetime | None]:
    """Normalize and auto-correct inverted date ranges."""
    normalized_start = normalize_datetime(start_date)
    normalized_end = normalize_datetime(end_date)
    if normalized_start and normalized_end and normalized_start > normalized_end:
        logger.warning(
            "Swapping inverted date range",
            start_date=normalized_start.isoformat(),
            end_date=normalized_end.isoformat(),
        )
        return normalized_end, normalized_start
    return normalized_start, normalized_end


# ═══════════════════════════════════════════════════════════════════
# ORDER LIST & DETAIL
# ═══════════════════════════════════════════════════════════════════

@router.get(
    "/export.csv",
    summary="Export orders as CSV",
    description="""
    Export orders as a CSV file.
    
    **Access:** Staff and above
    
    **Notes:**
    - Returns one row per order item (order fields repeated per item)
    - Use filters to scope exports
    """,
    responses={
        200: {
            "description": "CSV file download",
            "content": {"text/csv": {}},
        },
    },
    dependencies=[RequireStaff],
)
async def export_orders_csv(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: OrderType | None = Query(default=None, alias="type"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=10000, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """Export orders as CSV for reporting."""
    logger.info(
        "Exporting orders CSV",
        user=user.sub,
        status=status_filter,
        order_type=type_filter,
        search=search,
        limit=limit,
        offset=offset,
    )

    try:
        resolved_status = parse_status_filter(status_filter)
        normalized_start, normalized_end = normalize_date_range(start_date, end_date)
        rows = await order_service.export_orders_csv(
            db,
            status=resolved_status,
            order_type=type_filter,
            start_date=normalized_start,
            end_date=normalized_end,
            search=search,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        handle_service_error(e)
        raise

    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        fieldnames = [
            "order_id",
            "created_at",
            "status",
            "type",
            "time_slot",
            "customer_name",
            "customer_phone",
            "customer_email",
            "delivery_address",
            "delivery_suburb",
            "subtotal",
            "gst",
            "delivery_fee",
            "total",
            "notes",
            "item_id",
            "item_sku",
            "item_name",
            "item_quantity",
            "item_price",
            "item_checked",
            "substitution_status",
            "substitution_reason",
            "substitute_item_id",
            "substitute_name",
            "substitute_price",
            "substitution_qty",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

    output.seek(0)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"orders_export_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/export/email",
    response_model=OrderExportEmailResponse,
    summary="Email orders export",
    description="Queue a background export job and email the CSV to the current user.",
    dependencies=[RequireStaff],
)
async def email_orders_export(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: OrderType | None = Query(default=None, alias="type"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=10000, ge=1, le=100000),
    offset: int = Query(default=0, ge=0),
) -> OrderExportEmailResponse:
    """Queue background export and email CSV to current user."""
    logger.info(
        "Queueing orders export email",
        user=user.sub,
        status=status_filter,
        order_type=type_filter,
    )

    resolved_status = parse_status_filter(status_filter)
    to_email = await get_user_email(db, user.sub)
    normalized_start, normalized_end = normalize_date_range(start_date, end_date)

    task = export_orders_email.delay(
        "adhoc-email",
        to_email,
        {
            "status": resolved_status.value if resolved_status else None,
            "order_type": type_filter.value if type_filter else None,
            "start_date": normalized_start.isoformat() if normalized_start else None,
            "end_date": normalized_end.isoformat() if normalized_end else None,
            "search": search,
            "limit": limit,
            "offset": offset,
        },
    )

    return OrderExportEmailResponse(
        status="queued",
        message="Order export queued; CSV will be emailed shortly.",
        task_id=task.id,
    )


@router.post(
    "/export",
    response_model=OrderExportJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create order export job",
    description="Queue an export job and email the CSV to the destination address.",
    dependencies=[RequireStaff],
)
async def create_order_export(
    request: OrderExportRequest,
    user: CurrentUser,
    db: DbSession,
) -> OrderExportJobResponse:
    """Create export job and enqueue background processing."""
    resolved_status = parse_status_filter(request.status)
    destination_email = request.destination_email or await get_user_email(db, user.sub)
    normalized_start, normalized_end = normalize_date_range(
        request.start_date,
        request.end_date,
    )

    filters = {
        "status": resolved_status.value if resolved_status else None,
        "order_type": request.order_type.value if request.order_type else None,
        "start_date": normalized_start.isoformat() if normalized_start else None,
        "end_date": normalized_end.isoformat() if normalized_end else None,
        "search": request.search,
    }

    job = await order_service.create_export_job(
        db,
        requested_by=user.sub,
        destination_email=destination_email,
        filters=filters,
    )

    export_orders_email.delay(
        job.id,
        destination_email,
        {
            **filters,
            "limit": 100000,
            "offset": 0,
        },
    )

    return OrderExportJobResponse(
        job_id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        destination_email=job.destination_email,
        requested_at=job.created_at,
        file_url=job.file_url,
        error_message=job.error_message,
    )


@router.get(
    "/export/{job_id}",
    response_model=OrderExportJobResponse,
    summary="Get export job status",
    description="Get status and result metadata for an export job.",
    dependencies=[RequireStaff],
)
async def get_order_export_status(
    job_id: str,
    user: CurrentUser,
    db: DbSession,
) -> OrderExportJobResponse:
    """Return export job status for polling."""
    job = await order_service.get_export_job(db, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Export job not found",
        )

    if job.requested_by != user.sub:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this export job.",
        )

    return OrderExportJobResponse(
        job_id=job.id,
        status=job.status.value if hasattr(job.status, "value") else str(job.status),
        destination_email=job.destination_email,
        requested_at=job.created_at,
        file_url=job.file_url,
        error_message=job.error_message,
    )
@router.get(
    "/summary",
    response_model=OrderStatusSummaryResponse,
    summary="Order status summary",
    description="Get counts of orders by status for dashboard badges.",
    dependencies=[RequireStaff],
)
async def get_order_summary(
    user: CurrentUser,
    db: DbSession,
) -> OrderStatusSummaryResponse:
    """Return order status counts for summary cards."""
    logger.info("Fetching order summary", user=user.sub)

    try:
        summary = await order_service.get_status_summary(db)
        return OrderStatusSummaryResponse(**summary)
    except Exception as e:
        handle_service_error(e)
        raise


@router.get(
    "",
    response_model=OrderListResponse,
    summary="List orders",
    description="List orders with filters, search, and pagination.",
    dependencies=[RequireStaff],
)
async def list_orders(
    user: CurrentUser,
    db: DbSession,
    status_filter: str | None = Query(default=None, alias="status"),
    type_filter: OrderType | None = Query(default=None, alias="type"),
    start_date: datetime | None = Query(default=None),
    end_date: datetime | None = Query(default=None),
    search: str | None = Query(default=None, max_length=100),
    customer_name: str | None = Query(default=None, alias="customer"),
    customer_name_explicit: str | None = Query(default=None, alias="customer_name"),
    limit: int = Query(default=15, ge=1, le=15),
    offset: int = Query(default=0, ge=0),
    ordering: str | None = Query(default=None),
) -> OrderListResponse:
    """List orders for the grid/tabs view."""
    logger.info(
        "Listing orders",
        user=user.sub,
        status=status_filter,
        order_type=type_filter,
        search=search,
    )

    try:
        resolved_status = parse_status_filter(status_filter)
        normalized_start, normalized_end = normalize_date_range(start_date, end_date)
        ordering_field, ordering_desc = parse_ordering(ordering)
        explicit_customer = customer_name_explicit or customer_name

        orders, total = await order_service.list_orders(
            db,
            OrderListFilters(
                status=resolved_status,
                order_type=type_filter,
                start_date=normalized_start,
                end_date=normalized_end,
                search=search,
                customer_name=explicit_customer,
                ordering_field=ordering_field,
                ordering_desc=ordering_desc,
                limit=limit,
                offset=offset,
            ),
        )
        return OrderListResponse(
            items=[OrderSummaryResponse.model_validate(order) for order in orders],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.get(
    "/{order_id}",
    response_model=OrderDetailResponse,
    summary="Get order detail",
    description="Get full order detail including substitutions and status history.",
    dependencies=[RequireStaff],
)
async def get_order_detail(
    order_id: str,
    user: CurrentUser,
    db: DbSession,
) -> OrderDetailResponse:
    """Get full order detail for modal display."""
    logger.info("Fetching order detail", order_id=order_id, user=user.sub)

    try:
        order = await order_service.get_order(db, order_id)
        return OrderDetailResponse.model_validate(order)
    except Exception as e:
        handle_service_error(e)
        raise


# ═══════════════════════════════════════════════════════════════════
# ORDER UPDATES
# ═══════════════════════════════════════════════════════════════════

@router.patch(
    "/{order_id}/status",
    response_model=OrderOperationResponse,
    summary="Update order status",
    description="Update order status and return updated order.",
    dependencies=[RequireStaff],
)
async def update_order_status(
    order_id: str,
    request: UpdateOrderStatusRequest,
    user: CurrentUser,
    db: DbSession,
) -> OrderOperationResponse:
    """Update order status."""
    logger.info(
        "Updating order status",
        order_id=order_id,
        status=request.status,
        user=user.sub,
    )

    try:
        order = await order_service.update_status(db, order_id, request.status, user.sub)
        return OrderOperationResponse(
            order_id=order.id,
            status=order.status,
            timestamp=datetime.now(UTC),
            order=OrderDetailResponse.model_validate(order),
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.patch(
    "/{order_id}/items/{item_id}",
    response_model=OrderItemUpdateResponse,
    summary="Update item checklist",
    description="Update the pick/pack checklist flag for an item.",
    dependencies=[RequireStaff],
)
async def update_order_item_checklist(
    order_id: str,
    item_id: str,
    request: UpdateOrderItemChecklistRequest,
    user: CurrentUser,
    db: DbSession,
) -> OrderItemUpdateResponse:
    """Update checklist status for a single item."""
    logger.info(
        "Updating checklist",
        order_id=order_id,
        item_id=item_id,
        checked=request.checked,
        user=user.sub,
    )

    try:
        item = await order_service.update_item_checklist(
            db,
            order_id,
            item_id,
            request.checked,
        )
        order = await order_service.get_order(db, order_id)
        item_response = None
        for order_item in order.items:
            if order_item.id == item.id:
                item_response = OrderItemResponse.model_validate(order_item)
                break
        return OrderItemUpdateResponse(
            order_id=order.id,
            status=order.status,
            timestamp=datetime.now(UTC),
            item=item_response or OrderItemResponse.model_validate(item),
            order=OrderDetailResponse.model_validate(order),
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/{order_id}/substitutions",
    response_model=OrderOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create substitution",
    description="Add or update a substitution for an order item.",
    dependencies=[RequireStaff],
)
async def create_substitution(
    order_id: str,
    request: CreateSubstitutionRequest,
    user: CurrentUser,
    db: DbSession,
) -> OrderOperationResponse:
    """Create or update an item substitution."""
    logger.info(
        "Creating substitution",
        order_id=order_id,
        item_id=request.original_item_id,
        user=user.sub,
    )

    try:
        order = await order_service.create_substitution(
            db,
            order_id,
            request.original_item_id,
            SubstitutionInput(
                original_item_id=request.original_item_id,
                substitute_item_id=request.substitute_item_id,
                quantity=request.quantity,
                reason=request.reason,
                status=request.status,
                price_difference=request.price_difference,
                customer_notified=request.customer_notified,
            ),
        )
        return OrderOperationResponse(
            order_id=order.id,
            status=order.status,
            timestamp=datetime.now(UTC),
            order=OrderDetailResponse.model_validate(order),
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/{order_id}/contact",
    response_model=OrderContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Log contact attempt",
    description="Log a contact attempt for the order.",
    dependencies=[RequireStaff],
)
async def log_contact_attempt(
    order_id: str,
    request: LogContactAttemptRequest,
    user: CurrentUser,
    db: DbSession,
) -> OrderContactResponse:
    """Log a contact attempt for an order."""
    logger.info(
        "Logging contact attempt",
        order_id=order_id,
        channel=request.channel,
        user=user.sub,
    )

    try:
        order, attempt = await order_service.log_contact_attempt(
            db,
            order_id,
            request.channel,
            request.template_id,
            request.notes,
        )
        return OrderContactResponse(
            order_id=order.id,
            status=order.status,
            timestamp=datetime.now(UTC),
            contact=OrderContactAttemptResponse.model_validate(attempt),
            order=OrderDetailResponse.model_validate(order),
        )
    except Exception as e:
        handle_service_error(e)
        raise
