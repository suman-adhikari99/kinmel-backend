"""
POS API Router
--------------
Barcode lookup for point-of-sale scanning.
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status

from src.api.deps import CurrentUser, DbSession, RequireStaff
from src.core.exceptions import (
    ConcurrencyError,
    InsufficientStockError,
    NotFoundError,
    ValidationError,
)
from src.core.logging import get_logger
from src.modules.pos.schemas import (
    PosCatalogBootstrapResponse,
    PosCatalogChangesResponse,
    PosCheckoutCancelRequest,
    PosCheckoutCancelResponse,
    PosCheckoutCommitRequest,
    PosCheckoutReceiptResponse,
    PosCheckoutStartRequest,
    PosCheckoutStartResponse,
    PosLookupResponse,
)
from src.modules.pos.service import pos_service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/pos",
    tags=["POS"],
)


def parse_since(value: str) -> datetime:
    trimmed = value.strip()
    if not trimmed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE", "message": "since is required"},
        )
    normalized = trimmed.replace("Z", "+00:00") if trimmed.endswith("Z") else trimmed
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE", "message": "Invalid datetime format"},
        ) from exc
    if parsed.tzinfo is None:
        return parsed
    return parsed.astimezone(UTC)


def handle_service_error(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": exc.staff_message,
                "code": "NOT_FOUND",
                "resource": exc.details.get("resource"),
                "identifier": exc.details.get("identifier"),
            },
        )
    if isinstance(exc, InsufficientStockError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": exc.staff_message,
                "code": "INSUFFICIENT_STOCK",
                "sku": exc.details.get("sku"),
                "requested": exc.details.get("requested"),
                "available": exc.details.get("available"),
            },
        )
    if isinstance(exc, ConcurrencyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": exc.staff_message,
                "code": "CONCURRENT_MODIFICATION",
            },
        )
    if isinstance(exc, ValidationError):
        code = exc.details.get("code")
        status_code = status.HTTP_409_CONFLICT if code in {
            "RESERVATION_EXPIRED",
            "SALE_ALREADY_COMMITTED",
            "SALE_NOT_RESERVED",
            "IDEMPOTENCY_MISMATCH",
        } else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(
            status_code=status_code,
            detail={
                "message": exc.staff_message,
                "code": code or "VALIDATION_ERROR",
                "field": exc.details.get("field"),
            },
        )
    logger.exception("Unexpected POS error")
    raise exc


@router.get(
    "/lookup",
    response_model=PosLookupResponse,
    summary="Lookup product by barcode",
    description="Resolve a barcode into minimal product details.",
    dependencies=[RequireStaff],
)
async def lookup_barcode(
    db: DbSession,
    barcode: Annotated[str, Query(min_length=1, description="Scanned barcode")],
) -> PosLookupResponse:
    try:
        result = await pos_service.lookup_product(db, barcode=barcode)
        return PosLookupResponse(**result)
    except Exception as exc:
        handle_service_error(exc)
        raise


@router.get(
    "/catalog/bootstrap",
    response_model=PosCatalogBootstrapResponse,
    summary="Catalog bootstrap",
    description="Full catalog snapshot for POS cache.",
    dependencies=[RequireStaff],
)
async def catalog_bootstrap(
    db: DbSession,
) -> PosCatalogBootstrapResponse:
    return await pos_service.bootstrap_catalog(db)


@router.get(
    "/catalog/changes",
    response_model=PosCatalogChangesResponse,
    summary="Catalog changes",
    description="Catalog delta since sync token.",
    dependencies=[RequireStaff],
)
async def catalog_changes(
    db: DbSession,
    since: Annotated[str, Query(min_length=1, description="ISO datetime sync token")],
) -> PosCatalogChangesResponse:
    since_dt = parse_since(since)
    return await pos_service.catalog_changes(db, since_dt)


@router.post(
    "/checkout/start",
    response_model=PosCheckoutStartResponse,
    summary="Start checkout",
    description="Reserve stock for a POS checkout.",
    dependencies=[RequireStaff],
)
async def checkout_start(
    request: PosCheckoutStartRequest,
    user: CurrentUser,
    db: DbSession,
) -> PosCheckoutStartResponse:
    try:
        return await pos_service.start_checkout(db, request, user_id=user.sub)
    except Exception as exc:
        handle_service_error(exc)
        raise


@router.post(
    "/checkout/commit",
    response_model=PosCheckoutReceiptResponse,
    summary="Commit checkout",
    description="Fulfill a reserved POS checkout.",
    dependencies=[RequireStaff],
)
async def checkout_commit(
    request: PosCheckoutCommitRequest,
    user: CurrentUser,
    db: DbSession,
) -> PosCheckoutReceiptResponse:
    try:
        return await pos_service.commit_checkout(
            db,
            request.sale_id,
            idempotency_key=request.idempotency_key,
            user_id=user.sub,
        )
    except Exception as exc:
        handle_service_error(exc)
        raise


@router.get(
    "/checkout/by-key/{idempotency_key}",
    response_model=PosCheckoutStartResponse,
    summary="Lookup checkout by idempotency key",
    description="Fetch a checkout reservation by idempotency key.",
    dependencies=[RequireStaff],
)
async def checkout_by_key(
    db: DbSession,
    idempotency_key: Annotated[str, Path(min_length=8, max_length=100)],
) -> PosCheckoutStartResponse:
    try:
        return await pos_service.get_checkout_by_key(db, idempotency_key)
    except Exception as exc:
        handle_service_error(exc)
        raise


@router.get(
    "/checkout/{sale_id}",
    response_model=PosCheckoutStartResponse,
    summary="Get checkout status",
    description="Fetch a checkout reservation by sale ID.",
    dependencies=[RequireStaff],
)
async def checkout_status(
    db: DbSession,
    sale_id: Annotated[str, Path(min_length=1)],
) -> PosCheckoutStartResponse:
    try:
        return await pos_service.get_checkout_status(db, sale_id)
    except Exception as exc:
        handle_service_error(exc)
        raise


@router.post(
    "/checkout/cancel",
    response_model=PosCheckoutCancelResponse,
    summary="Cancel checkout",
    description="Cancel a reserved POS checkout and release stock.",
    dependencies=[RequireStaff],
)
async def checkout_cancel(
    request: PosCheckoutCancelRequest,
    user: CurrentUser,
    db: DbSession,
) -> PosCheckoutCancelResponse:
    try:
        sale_id, status_value = await pos_service.cancel_checkout(
            db,
            request.sale_id,
            user_id=user.sub,
        )
        return PosCheckoutCancelResponse(sale_id=sale_id, status=status_value)
    except Exception as exc:
        handle_service_error(exc)
        raise
