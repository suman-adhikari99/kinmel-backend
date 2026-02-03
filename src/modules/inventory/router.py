"""
Inventory API Router
--------------------
REST endpoints for inventory operations.

🔐 ROLE-BASED ACCESS CONTROL:

| Endpoint         | STAFF | MANAGER | OWNER |
|------------------|-------|---------|-------|
| receive_stock    | ✓     | ✓       | ✓     |
| adjust_stock     | ✗     | ✓       | ✓     |
| reserve_stock    | ✓     | ✓       | ✓     |
| release_stock    | ✓     | ✓       | ✓     |
| fulfill_order    | ✓     | ✓       | ✓     |
| dispose_stock    | ✗     | ✓       | ✓     |
| get_stock        | ✓     | ✓       | ✓     |
| get_low_stock    | ✓     | ✓       | ✓     |
| get_history      | ✓     | ✓       | ✓     |

Design Principles:
1. Routes are thin - all logic in service layer
2. Explicit role checks with clear denied errors
3. Consistent response format
4. Correlation IDs in all responses
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from src.api.deps import (
    CurrentUser,
    DbSession,
    RequireManager,
    RequireStaff,
)
from src.core.exceptions import (
    ConcurrencyError,
    InsufficientStockError,
    NotFoundError,
    StockAdjustmentTooLargeError,
    ValidationError,
)
from src.core.logging import get_correlation_id, get_logger
from src.core.security import Role, has_role_or_higher
from src.modules.inventory.schemas import (
    AdjustStockRequest,
    DisposeStockRequest,
    ExpiringBatchResponse,
    ExpiryWatchResponse,
    ExpiryWatchItemResponse,
    FulfillOrderRequest,
    InventoryHistoryResponse,
    InventoryHistoryItemResponse,
    InventoryImportResponse,
    InventoryListResponse,
    InventoryListItemResponse,
    InventorySummaryResponse,
    InventoryItemResponse,
    LocationSummary,
    LowStockAlertResponse,
    MovementHistoryResponse,
    ReceiveStockRequest,
    ReleaseReservationRequest,
    ReserveStockRequest,
    StockLevelResponse,
    StockMovementResponse,
    StockOperationResponse,
    UpdateStockRequest,
    UpdateStockResponse,
    UpdateThresholdRequest,
    UpdateThresholdResponse,
    RestockPriorityResponse,
    RestockPriorityItemResponse,
)
from src.modules.inventory.service import (
    AdjustmentInput,
    ReceivingInput,
    ReservationInput,
    inventory_service,
)
from src.modules.inventory.models import LocationType
from src.modules.products.category_repository import category_repository

logger = get_logger(__name__)

router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Resource not found"},
        409: {"description": "Conflict (concurrent modification)"},
        422: {"description": "Validation error or business rule violation"},
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def require_manager_or_owner(user: CurrentUser) -> None:
    """
    Verify user has manager or owner role.
    
    Raises HTTPException 403 if insufficient permissions.
    """
    if not has_role_or_higher(user.role, Role.MANAGER):
        logger.warning(
            "Access denied - insufficient role",
            user_id=user.sub,
            user_role=user.role,
            required_role="MANAGER",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "This action requires Manager or Owner role.",
                "code": "INSUFFICIENT_ROLE",
                "required_role": "MANAGER",
                "your_role": user.role.value,
            },
        )


def build_operation_response(result, message: str) -> StockOperationResponse:
    """Build standard operation response from service result."""
    return StockOperationResponse(
        success=True,
        message=message,
        item=InventoryItemResponse.model_validate(result.inventory_item),
        movement=StockMovementResponse.model_validate(result.movement),
        previous_stock=result.previous_stock,
        new_stock=result.new_stock,
    )


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
    elif isinstance(e, InsufficientStockError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.staff_message,
                "code": "INSUFFICIENT_STOCK",
                "requested": e.details.get("requested"),
                "available": e.details.get("available"),
            },
        )
    elif isinstance(e, StockAdjustmentTooLargeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.staff_message,
                "code": "ADJUSTMENT_TOO_LARGE",
                "adjustment": e.details.get("adjustment"),
                "threshold_percent": e.details.get("threshold_percent"),
            },
        )
    elif isinstance(e, ConcurrencyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": e.staff_message,
                "code": "CONCURRENT_MODIFICATION",
                "action": "Please refresh and try again.",
            },
        )
    elif isinstance(e, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": e.staff_message,
                "code": "VALIDATION_ERROR",
                "field": e.details.get("field"),
            },
        )
    else:
        # Unknown error - log and re-raise
        logger.exception("Unexpected error in inventory operation")
        raise


def compute_stock_status(stock: int, reorder_point: int) -> str:
    if stock <= 0:
        return "out_of_stock"
    if stock <= reorder_point:
        return "low_stock"
    return "in_stock"


def to_gst(unit_price: Decimal, tax_rate: Decimal) -> Decimal:
    return (unit_price * tax_rate).quantize(Decimal("0.01"))


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY & LIST
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/summary",
    response_model=InventorySummaryResponse,
    summary="Inventory summary",
    dependencies=[RequireStaff],
)
async def get_inventory_summary(
    user: CurrentUser,
    db: DbSession,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> InventorySummaryResponse:
    summary = await inventory_service.get_inventory_summary(
        db,
        location_id=location_id,
    )
    return InventorySummaryResponse(**summary)


@router.get(
    "/locations",
    response_model=list[LocationSummary],
    summary="List locations",
    description="List active inventory locations for POS checkout.",
    dependencies=[RequireStaff],
)
async def list_locations(
    db: DbSession,
    code: Annotated[str | None, Query(description="Filter by location code")] = None,
    location_type: Annotated[LocationType | None, Query(description="Filter by location type")] = None,
) -> list[LocationSummary]:
    try:
        if code:
            location = await inventory_service.get_location_by_code(db, code)
            return [LocationSummary.model_validate(location)]
        locations = await inventory_service.list_locations(db, location_type=location_type)
        return [LocationSummary.model_validate(location) for location in locations]
    except Exception as e:
        handle_service_error(e)
        raise


@router.get(
    "",
    response_model=InventoryListResponse,
    summary="Inventory list",
    dependencies=[RequireStaff],
)
async def list_inventory(
    db: DbSession,
    search: Annotated[str | None, Query(description="Search SKU or name")] = None,
    category_id: Annotated[str | None, Query(description="Filter by category")] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status", pattern="^(in_stock|low_stock|out_of_stock)$"),
    ] = None,
    low_stock_only: Annotated[bool, Query(description="Only low stock items")] = False,
    out_of_stock_only: Annotated[bool, Query(description="Only out of stock items")] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[
        str,
        Query(description="Sort field", pattern="^(sku|name|stock|updated_at|category)$"),
    ] = "updated_at",
    order: Annotated[
        str,
        Query(description="Sort order", pattern="^(asc|desc)$"),
    ] = "desc",
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> InventoryListResponse:
    items, total = await inventory_service.list_inventory_items(
        db,
        location_id=location_id,
        search=search,
        category=category_id,
        status=status,
        low_stock_only=low_stock_only,
        out_of_stock_only=out_of_stock_only,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )
    category_names = list({item.product.category for item in items})
    categories = await category_repository.list_by_names(db, category_names)
    category_map = {category.name.lower(): category.id for category in categories}
    response_items = [
        InventoryListItemResponse(
            sku=item.product.sku,
            name=item.product.name,
            category=item.product.category,
            category_id=category_map.get(item.product.category.lower(), item.product.category),
            variant=None,
            stock=item.physical_stock,
            threshold=item.reorder_point,
            price=item.product.unit_price,
            gst=to_gst(item.product.unit_price, item.product.tax_rate),
            status=compute_stock_status(item.physical_stock, item.reorder_point),
            last_updated=item.updated_at,
        )
        for item in items
    ]
    return InventoryListResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=response_items,
    )


# ═══════════════════════════════════════════════════════════════════════════
# STOCK OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/receive",
    response_model=StockOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Receive stock",
    description="""
    Record incoming stock from suppliers or transfers.
    
    **Who can use:** Staff, Managers, Owners
    
    Creates an audit trail and optionally tracks batch/expiry for perishables.
    """,
    dependencies=[RequireStaff],
)
async def receive_stock(
    request: ReceiveStockRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """
    Receive new stock into inventory.
    
    - Creates inventory record if first time at this location
    - Creates batch record if expiry_date provided
    - Logs movement for audit trail
    """
    logger.info(
        "Receiving stock",
        sku=request.sku,
        location=request.location_id,
        quantity=request.quantity,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.receive_stock(
            db,
            ReceivingInput(
                sku=request.sku,
                location_id=request.location_id,
                quantity=request.quantity,
                user_id=user.sub,
                batch_number=request.batch_number,
                expiry_date=request.expiry_date,
                cost_per_unit=request.cost_per_unit,
                reference_id=request.reference_id,
                notes=request.notes,
            ),
        )
        
        return build_operation_response(
            result,
            f"Received {request.quantity} units of {request.sku}",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/adjust",
    response_model=StockOperationResponse,
    summary="Adjust stock",
    description="""
    Manually adjust stock to a new quantity.
    
    **Who can use:** Managers and Owners ONLY
    
    ⚠️ Large adjustments (>50% of current stock) require confirmation.
    
    Use cases:
    - Cycle count corrections
    - Shrinkage recording
    - Audit corrections
    """,
)
async def adjust_stock(
    request: AdjustStockRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """
    Manually adjust stock quantity.
    
    🔐 MANAGER/OWNER ONLY
    """
    # Explicit role check with detailed error
    require_manager_or_owner(user)
    
    logger.info(
        "Adjusting stock",
        sku=request.sku,
        location=request.location_id,
        new_quantity=request.new_quantity,
        reason=request.reason,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.adjust_stock(
            db,
            AdjustmentInput(
                sku=request.sku,
                location_id=request.location_id,
                new_quantity=request.new_quantity,
                user_id=user.sub,
                reason=request.reason,
                notes=request.notes,
                skip_large_adjustment_check=request.confirm_large_adjustment,
            ),
        )
        
        delta = result.new_stock - result.previous_stock
        direction = "increased" if delta > 0 else "decreased"
        
        return build_operation_response(
            result,
            f"Stock {direction} by {abs(delta)} units (now {result.new_stock})",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/reserve",
    response_model=StockOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reserve stock",
    description="""
    Reserve stock for an online order.
    
    **Who can use:** Staff, Managers, Owners
    
    Increases buffer, reducing online_available without changing physical stock.
    """,
    dependencies=[RequireStaff],
)
async def reserve_stock(
    request: ReserveStockRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """Reserve stock for an order."""
    logger.info(
        "Reserving stock",
        sku=request.sku,
        location=request.location_id,
        quantity=request.quantity,
        order_id=request.order_id,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.reserve_stock(
            db,
            ReservationInput(
                sku=request.sku,
                location_id=request.location_id,
                quantity=request.quantity,
                user_id=user.sub,
                order_id=request.order_id,
                notes=request.notes,
            ),
        )
        
        return build_operation_response(
            result,
            f"Reserved {request.quantity} units for order {request.order_id}",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/release",
    response_model=StockOperationResponse,
    summary="Release reservation",
    description="""
    Release a stock reservation.
    
    **Who can use:** Staff, Managers, Owners
    
    Call when:
    - Order is cancelled
    - Reservation expires
    """,
    dependencies=[RequireStaff],
)
async def release_reservation(
    request: ReleaseReservationRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """Release a stock reservation."""
    logger.info(
        "Releasing reservation",
        sku=request.sku,
        location=request.location_id,
        quantity=request.quantity,
        order_id=request.order_id,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.release_reservation(
            db,
            sku=request.sku,
            location_id=request.location_id,
            quantity=request.quantity,
            user_id=user.sub,
            order_id=request.order_id,
            notes=request.notes,
        )
        
        return build_operation_response(
            result,
            f"Released {request.quantity} units from order {request.order_id}",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/fulfill",
    response_model=StockOperationResponse,
    summary="Fulfill order",
    description="""
    Fulfill an order by decrementing stock.
    
    **Who can use:** Staff (cashiers), Managers, Owners
    
    Decreases both physical stock and buffer.
    """,
    dependencies=[RequireStaff],
)
async def fulfill_order(
    request: FulfillOrderRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """Fulfill an order (sell stock)."""
    logger.info(
        "Fulfilling order",
        sku=request.sku,
        location=request.location_id,
        quantity=request.quantity,
        order_id=request.order_id,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.fulfill_order(
            db,
            sku=request.sku,
            location_id=request.location_id,
            quantity=request.quantity,
            user_id=user.sub,
            order_id=request.order_id,
            notes=request.notes,
        )
        
        return build_operation_response(
            result,
            f"Sold {request.quantity} units ({result.new_stock} remaining)",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.post(
    "/dispose",
    response_model=StockOperationResponse,
    summary="Dispose stock",
    description="""
    Dispose of expired or damaged stock.
    
    **Who can use:** Managers and Owners ONLY
    
    Creates detailed audit record for loss tracking.
    """,
)
async def dispose_stock(
    request: DisposeStockRequest,
    user: CurrentUser,
    db: DbSession,
) -> StockOperationResponse:
    """
    Dispose of stock (expired, damaged, etc.).
    
    🔐 MANAGER/OWNER ONLY
    """
    # Explicit role check
    require_manager_or_owner(user)
    
    logger.info(
        "Disposing stock",
        sku=request.sku,
        location=request.location_id,
        quantity=request.quantity,
        reason=request.reason,
        user=user.sub,
    )
    
    try:
        result = await inventory_service.dispose_stock(
            db,
            sku=request.sku,
            location_id=request.location_id,
            quantity=request.quantity,
            user_id=user.sub,
            reason=request.reason,
            batch_id=request.batch_id,
            notes=request.notes,
        )
        
        return build_operation_response(
            result,
            f"Disposed {request.quantity} units ({request.reason.value})",
        )
        
    except Exception as e:
        handle_service_error(e)
        raise


@router.patch(
    "/{sku}/stock",
    response_model=UpdateStockResponse,
    summary="Update stock",
    dependencies=[RequireManager],
)
async def update_stock(
    sku: str,
    request: UpdateStockRequest,
    user: CurrentUser,
    db: DbSession,
) -> UpdateStockResponse:
    try:
        result = await inventory_service.update_stock_level(
            db,
            sku=sku.upper(),
            location_id=request.location_id,
            new_stock=request.stock,
            user_id=user.sub,
        )
        item = result.inventory_item
        return UpdateStockResponse(
            sku=item.product.sku,
            stock=item.physical_stock,
            status=compute_stock_status(item.physical_stock, item.reorder_point),
            last_updated=item.updated_at,
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.patch(
    "/{sku}/threshold",
    response_model=UpdateThresholdResponse,
    summary="Update alert threshold",
    dependencies=[RequireManager],
)
async def update_threshold(
    sku: str,
    request: UpdateThresholdRequest,
    user: CurrentUser,
    db: DbSession,
) -> UpdateThresholdResponse:
    try:
        item = await inventory_service.update_threshold(
            db,
            sku=sku.upper(),
            location_id=request.location_id,
            new_threshold=request.threshold,
        )
        return UpdateThresholdResponse(
            sku=item.product.sku,
            threshold=item.reorder_point,
        )
    except Exception as e:
        handle_service_error(e)
        raise


@router.get(
    "/{sku}/history",
    response_model=InventoryHistoryResponse,
    summary="Inventory history",
    dependencies=[RequireStaff],
)
async def get_inventory_history(
    sku: str,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> InventoryHistoryResponse:
    movements, total = await inventory_service.get_movement_history_by_sku(
        db,
        sku=sku.upper(),
        location_id=location_id,
        limit=limit,
        offset=offset,
    )
    items = [
        InventoryHistoryItemResponse(
            type=m.movement_type.value,
            change=m.quantity_delta,
            stock=m.quantity_after,
            at=m.created_at,
            user=m.user_id,
            source=m.reference_type or (m.reason.value if m.reason else None),
        )
        for m in movements
    ]
    return InventoryHistoryResponse(items=items, total=total)


@router.get(
    "/restock-priorities",
    response_model=RestockPriorityResponse,
    summary="Restock priorities",
    dependencies=[RequireStaff],
)
async def get_restock_priorities(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> RestockPriorityResponse:
    items = await inventory_service.get_low_stock_alerts(
        db,
        location_id=location_id,
    )
    response_items = [
        RestockPriorityItemResponse(
            sku=item.product.sku,
            name=item.product.name,
            stock=item.physical_stock,
            threshold=item.reorder_point,
            supplier=None,
        )
        for item in items[:limit]
    ]
    return RestockPriorityResponse(items=response_items)


@router.get(
    "/expiry-watch",
    response_model=ExpiryWatchResponse,
    summary="Expiry watch",
    dependencies=[RequireStaff],
)
async def get_expiry_watch(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> ExpiryWatchResponse:
    batches = await inventory_service.get_expiring_soon(
        db,
        days_ahead=days,
        location_id=location_id,
    )
    response_items = [
        ExpiryWatchItemResponse(
            sku=batch.inventory_item.product.sku,
            name=batch.inventory_item.product.name,
            days_to_expire=batch.days_until_expiry or 0,
            batch=batch.batch_number,
        )
        for batch in batches[:limit]
    ]
    return ExpiryWatchResponse(items=response_items)


# ═══════════════════════════════════════════════════════════════════════════
# QUERY ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@router.get(
    "/stock/{sku}",
    response_model=StockLevelResponse,
    summary="Get stock level",
    description="Get current stock level for a SKU.",
    dependencies=[RequireStaff],
)
async def get_stock_level(
    sku: str,
    user: CurrentUser,
    db: DbSession,
    location_id: Annotated[str | None, Query(description="Specific location (optional)")] = None,
) -> StockLevelResponse:
    """Get stock level for a SKU, optionally filtered by location."""
    try:
        result = await inventory_service.get_stock_level(
            db,
            sku.upper(),
            location_id=location_id,
        )
        return StockLevelResponse(**result)
        
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": e.staff_message, "code": "NOT_FOUND"},
        )


@router.get(
    "/alerts/low-stock",
    response_model=list[LowStockAlertResponse],
    summary="Get low stock alerts",
    description="Get all items at or below reorder point.",
    dependencies=[RequireStaff],
)
async def get_low_stock_alerts(
    user: CurrentUser,
    db: DbSession,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> list[LowStockAlertResponse]:
    """Get items that need reordering."""
    items = await inventory_service.get_low_stock_alerts(db, location_id=location_id)
    
    return [
        LowStockAlertResponse.from_inventory_item(item)
        for item in items
    ]


@router.get(
    "/alerts/expiring",
    response_model=list[ExpiringBatchResponse],
    summary="Get expiring items",
    description="Get batches expiring within N days.",
    dependencies=[RequireStaff],
)
async def get_expiring_items(
    user: CurrentUser,
    db: DbSession,
    days_ahead: Annotated[int, Query(ge=1, le=90, description="Days to look ahead")] = 7,
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
) -> list[ExpiringBatchResponse]:
    """Get batches expiring soon."""
    batches = await inventory_service.get_expiring_soon(
        db,
        days_ahead=days_ahead,
        location_id=location_id,
    )
    
    return [
        ExpiringBatchResponse(
            batch_id=batch.id,
            sku=batch.inventory_item.product.sku,
            product_name=batch.inventory_item.product.name,
            location_code=batch.inventory_item.location.code,
            quantity=batch.quantity,
            expiry_date=batch.expiry_date,
            days_until_expiry=batch.days_until_expiry or 0,
            batch_number=batch.batch_number,
        )
        for batch in batches
    ]


@router.get(
    "/history/{sku}",
    response_model=MovementHistoryResponse,
    summary="Get movement history",
    description="Get stock movement audit trail for a SKU at a location.",
    dependencies=[RequireStaff],
)
async def get_movement_history(
    sku: str,
    user: CurrentUser,
    db: DbSession,
    location_id: Annotated[str, Query(description="Location ID")],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> MovementHistoryResponse:
    """Get movement history for audit."""
    try:
        movements = await inventory_service.get_movement_history(
            db,
            sku.upper(),
            location_id,
            limit=limit,
        )
        
        return MovementHistoryResponse(
            sku=sku.upper(),
            location_id=location_id,
            movements=[
                StockMovementResponse.model_validate(m)
                for m in movements
            ],
            total=len(movements),
        )
        
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": e.staff_message, "code": "NOT_FOUND"},
        )


@router.post(
    "/import",
    response_model=InventoryImportResponse,
    summary="Import inventory CSV",
    dependencies=[RequireManager],
)
async def import_inventory(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
    location_id: Annotated[str | None, Query(description="Target location")] = None,
) -> InventoryImportResponse:
    import csv
    import io

    contents = await file.read()
    decoded = contents.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(decoded))

    updated = 0
    low_stock_alerts = 0
    skipped = 0

    for row in reader:
        sku = (row.get("sku") or row.get("SKU") or "").strip().upper()
        stock_value = row.get("stock") or row.get("Stock")
        threshold_value = row.get("threshold") or row.get("Threshold") or row.get("reorder_point")
        if not sku:
            skipped += 1
            continue
        try:
            if stock_value is not None and str(stock_value).strip() != "":
                result = await inventory_service.update_stock_level(
                    db,
                    sku=sku,
                    location_id=location_id,
                    new_stock=int(stock_value),
                    user_id=user.sub,
                )
                item = result.inventory_item
            else:
                item = None

            if threshold_value is not None and str(threshold_value).strip() != "":
                item = await inventory_service.update_threshold(
                    db,
                    sku=sku,
                    location_id=location_id,
                    new_threshold=int(threshold_value),
                )
            if item is None:
                skipped += 1
                continue
            updated += 1
            if item.physical_stock <= item.reorder_point:
                low_stock_alerts += 1
        except Exception:
            skipped += 1
            continue

    await db.commit()
    return InventoryImportResponse(
        updated=updated,
        low_stock_alerts=low_stock_alerts,
        skipped=skipped,
    )


@router.get(
    "/export.csv",
    summary="Export inventory CSV",
    dependencies=[RequireManager],
)
async def export_inventory(
    db: DbSession,
    search: Annotated[str | None, Query(description="Search SKU or name")] = None,
    category_id: Annotated[str | None, Query(description="Filter by category")] = None,
    status: Annotated[
        str | None,
        Query(description="Filter by status", pattern="^(in_stock|low_stock|out_of_stock)$"),
    ] = None,
    low_stock_only: Annotated[bool, Query(description="Only low stock items")] = False,
    out_of_stock_only: Annotated[bool, Query(description="Only out of stock items")] = False,
    sort: Annotated[
        str,
        Query(description="Sort field", pattern="^(sku|name|stock|updated_at|category)$"),
    ] = "updated_at",
    order: Annotated[
        str,
        Query(description="Sort order", pattern="^(asc|desc)$"),
    ] = "desc",
    location_id: Annotated[str | None, Query(description="Filter by location")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    import csv
    import io
    from starlette.responses import StreamingResponse

    items, _ = await inventory_service.list_inventory_items(
        db,
        location_id=location_id,
        search=search,
        category=category_id,
        status=status,
        low_stock_only=low_stock_only,
        out_of_stock_only=out_of_stock_only,
        limit=limit,
        offset=offset,
        sort=sort,
        order=order,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "sku",
            "name",
            "category",
            "stock",
            "threshold",
            "price",
            "gst",
            "status",
            "last_updated",
        ]
    )
    for item in items:
        writer.writerow(
            [
                item.product.sku,
                item.product.name,
                item.product.category,
                item.physical_stock,
                item.reorder_point,
                item.product.unit_price,
                to_gst(item.product.unit_price, item.product.tax_rate),
                compute_stock_status(item.physical_stock, item.reorder_point),
                item.updated_at.isoformat() if item.updated_at else "",
            ]
        )

    output.seek(0)
    headers = {"Content-Disposition": "attachment; filename=inventory_export.csv"}
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers=headers)
