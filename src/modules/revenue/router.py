"""
Revenue API Router
------------------
Endpoints for revenue analytics.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from src.api.deps import CurrentUser, DbSession, RequireStaff
from src.core.exceptions import ValidationError
from src.core.logging import get_logger
from src.modules.revenue.schemas import (
    RevenueCategoriesResponse,
    RevenueCategoryItem,
    RevenueCategoryOthers,
    RevenueDailyByTypePoint,
    RevenueDailyByTypeResponse,
    RevenuePaymentMethod,
    RevenuePaymentMethodsResponse,
    RevenuePayoutSummaryResponse,
    RevenueSummaryResponse,
    RevenueTaxesFeesResponse,
    RevenueTotals,
    RevenueComparisons,
    RevenueTrendPoint,
    RevenueTrendResponse,
    RevenueTransactionsResponse,
    RevenueTransaction,
)
from src.modules.revenue.service import revenue_service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/revenue",
    tags=["Revenue"],
    dependencies=[RequireStaff],
)


def handle_revenue_error(exc: Exception) -> None:
    if isinstance(exc, ValidationError):
        code = "INVALID_RANGE" if exc.details.get("field") == "range" else "INVALID_REQUEST"
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": code, "message": exc.staff_message},
        )
    raise


def format_date(dt: datetime, timezone: str) -> str:
    return dt.astimezone(revenue_service.parse_timezone(timezone)).date().isoformat()


def normalize_timezone(value: str | None) -> str:
    return value.strip() if value and value.strip() else "UTC"


def parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    normalized = trimmed.replace("Z", "+00:00") if trimmed.endswith("Z") else trimmed
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_DATE", "message": "Invalid datetime format"},
        ) from exc


def resolve_range_with_defaults(
    range_value: str,
    timezone: str,
    from_date: datetime | None,
    to_date: datetime | None,
) -> "RevenueRange":
    """Resolve range, defaulting to range_value when from/to are missing."""
    if from_date is None or to_date is None:
        return revenue_service.resolve_range(range_value, timezone, None, None)
    return revenue_service.resolve_range("custom", timezone, from_date, to_date)


@router.get(
    "/summary",
    response_model=RevenueSummaryResponse,
    summary="Revenue summary",
)
async def get_revenue_summary(
    user: CurrentUser,
    db: DbSession,
    range: str = Query(default="month"),
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
) -> RevenueSummaryResponse:
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = revenue_service.resolve_range(range, timezone, from_date, to_date)
        result = await revenue_service.get_summary(db, current)
        return RevenueSummaryResponse(
            currency=currency,
            range=current.range_label,
            **{
                "from": format_date(current.start, timezone),
                "to": format_date(current.end, timezone),
            },
            totals=RevenueTotals(**result["totals"]),
            comparisons=RevenueComparisons(**result["comparisons"]),
            lastUpdated=datetime.now(UTC),
        )
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/trend",
    response_model=RevenueTrendResponse,
    summary="Revenue trend",
)
async def get_revenue_trend(
    user: CurrentUser,
    db: DbSession,
    interval: str = Query(default="month"),
    range: str = Query(default="month"),
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
) -> RevenueTrendResponse:
    if interval not in {"day", "week", "month"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_INTERVAL", "message": "Invalid interval"},
        )

    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        rows = await revenue_service.get_trend(db, current, interval, timezone)
        tz = revenue_service.parse_timezone(timezone)
        series = []
        for row in rows:
            period = row["period"]
            if period.tzinfo is None:
                period = period.replace(tzinfo=tz)
            label = period.strftime("%b") if interval == "month" else (
                f"Wk {period.strftime('%W')}" if interval == "week" else period.strftime("%a")
            )
            series.append(
                RevenueTrendPoint(
                    label=label,
                    startDate=period.date().isoformat(),
                    revenue=row["revenue"],
                    expenses=row["expenses"],
                    profit=row["revenue"] - row["expenses"],
                )
            )
        return RevenueTrendResponse(currency=currency, interval=interval, series=series)
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/daily-by-type",
    response_model=RevenueDailyByTypeResponse,
    summary="Daily revenue by type",
)
async def get_daily_by_type(
    user: CurrentUser,
    db: DbSession,
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    range: str = Query(default="month"),
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
    types: str | None = Query(default=None),
) -> RevenueDailyByTypeResponse:
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        type_list = types.split(",") if types else None
        rows = await revenue_service.get_daily_by_type(db, current, timezone, type_list)
        tz = revenue_service.parse_timezone(timezone)
        grouped: dict[str, dict[str, Decimal]] = {}
        for row in rows:
            period = row["period"]
            if period.tzinfo is None:
                period = period.replace(tzinfo=tz)
            date_key = period.date().isoformat()
            grouped.setdefault(date_key, {"pickup": Decimal("0"), "delivery": Decimal("0")})
            if row["order_type"] in {"pickup", "delivery"}:
                grouped[date_key][row["order_type"]] += row["revenue"]

        series = []
        for date_key in sorted(grouped.keys()):
            period = datetime.fromisoformat(date_key).replace(tzinfo=tz)
            series.append(
                RevenueDailyByTypePoint(
                    label=period.strftime("%a"),
                    date=date_key,
                    pickup=grouped[date_key]["pickup"],
                    delivery=grouped[date_key]["delivery"],
                )
            )

        return RevenueDailyByTypeResponse(currency=currency, series=series)
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/payment-methods",
    response_model=RevenuePaymentMethodsResponse,
    summary="Revenue by payment method",
)
async def get_payment_methods(
    user: CurrentUser,
    db: DbSession,
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    range: str = Query(default="month"),
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
) -> RevenuePaymentMethodsResponse:
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        rows = await revenue_service.get_payment_methods(db, current)
        total = sum((row["amount"] for row in rows), Decimal("0"))
        methods = []
        for row in rows:
            pct = (row["amount"] / total * Decimal("100")) if total else Decimal("0")
            name = row["method"].replace("_", " ").title()
            methods.append(
                RevenuePaymentMethod(
                    name=name,
                    value=pct.quantize(Decimal("1")),
                    amount=row["amount"],
                )
            )
        return RevenuePaymentMethodsResponse(currency=currency, methods=methods, total=total)
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/categories/top",
    response_model=RevenueCategoriesResponse,
    summary="Top revenue categories",
)
async def get_top_categories(
    user: CurrentUser,
    db: DbSession,
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    range: str = Query(default="month"),
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
    limit: int = Query(default=6, ge=1, le=20),
) -> RevenueCategoriesResponse:
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        rows = await revenue_service.get_categories(db, current)
        total = sum((row["revenue"] for row in rows), Decimal("0"))
        top_rows = rows[:limit]
        categories = []
        for row in top_rows:
            percentage = (row["revenue"] / total * Decimal("100")) if total else Decimal("0")
            categories.append(
                RevenueCategoryItem(
                    category=row["category"],
                    revenue=row["revenue"],
                    percentage=percentage.quantize(Decimal("1")),
                )
            )
        others_revenue = sum((row["revenue"] for row in rows[limit:]), Decimal("0"))
        others_pct = (others_revenue / total * Decimal("100")) if total else Decimal("0")
        return RevenueCategoriesResponse(
            currency=currency,
            categories=categories,
            others=RevenueCategoryOthers(
                revenue=others_revenue,
                percentage=others_pct.quantize(Decimal("1")),
            ),
        )
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/transactions",
    response_model=RevenueTransactionsResponse,
    summary="Recent transactions",
)
async def get_transactions(
    user: CurrentUser,
    db: DbSession,
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    range: str = Query(default="month"),
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
    limit: int = Query(default=5, ge=1, le=50),
    status: str | None = Query(default=None),
) -> RevenueTransactionsResponse:
    status_map = {"completed": "completed", "refunded": "cancelled", "failed": "cancelled"}
    mapped_status = status_map.get(status) if status else None
    if status and status not in status_map:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_STATUS", "message": "Invalid status"},
        )
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        rows = await revenue_service.get_transactions(db, current, mapped_status, limit)
        transactions = [
            RevenueTransaction(
                id=row["id"],
                customer=row["customer"],
                amount=row["amount"],
                method="Unknown",
                time=row["time"],
                status=row["status"],
            )
            for row in rows
        ]
        return RevenueTransactionsResponse(currency=currency, transactions=transactions)
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/payouts/summary",
    response_model=RevenuePayoutSummaryResponse,
    summary="Payout summary",
)
async def get_payout_summary(
    user: CurrentUser,
    db: DbSession,
    currency: str = Query(default="AUD"),
    timezone: str = Query(default="UTC"),
) -> RevenuePayoutSummaryResponse:
    current = revenue_service.resolve_range("month", timezone, None, None)
    summary = await revenue_service.get_payout_summary(db, current)
    next_payout = summary["next_payout"]
    last_payout = summary["last_payout"]
    return RevenuePayoutSummaryResponse(
        nextPayout=datetime.fromisoformat(next_payout) if next_payout else datetime.now(UTC),
        lastPayout=datetime.fromisoformat(last_payout) if last_payout else datetime.now(UTC),
        pendingAmount=summary["pending_amount"],
        completedThisMonth=summary["completed_count"],
        payoutFrequency=summary["payout_frequency"],
        processor=summary["processor"],
    )


@router.get(
    "/taxes-and-fees",
    response_model=RevenueTaxesFeesResponse,
    summary="Taxes and fees",
)
async def get_taxes_fees(
    user: CurrentUser,
    db: DbSession,
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    range: str = Query(default="month"),
    timezone: str = Query(default="UTC"),
    currency: str = Query(default="AUD"),
) -> RevenueTaxesFeesResponse:
    try:
        timezone = normalize_timezone(timezone)
        from_date = parse_optional_datetime(from_param)
        to_date = parse_optional_datetime(to_param)
        current = resolve_range_with_defaults(range, timezone, from_date, to_date)
        gst_collected = await revenue_service.get_gst_total(db, current)
        adjustments = await revenue_service.get_adjustments(db, current)
        gst_due = (current.end + timedelta(days=14)).date().isoformat()
        return RevenueTaxesFeesResponse(
            gstCollected=gst_collected,
            gstDue=gst_due,
            platformFees=adjustments["platform_fees"],
            refunds=adjustments["refunds"],
            disputes=adjustments["disputes"],
        )
    except Exception as exc:
        handle_revenue_error(exc)
        raise


@router.get(
    "/export",
    summary="Export revenue",
)
async def export_revenue(
    user: CurrentUser,
    db: DbSession,
    range: str = Query(default="month"),
    from_param: Annotated[str | None, Query(alias="from")] = None,
    to_param: Annotated[str | None, Query(alias="to")] = None,
    timezone: str = Query(default="UTC"),
    format: str = Query(default="csv"),
    sections: str | None = Query(default=None),
):
    if format != "csv":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_FORMAT", "message": "Only csv supported"},
        )
    if sections:
        section_list = [s.strip() for s in sections.split(",") if s.strip()]
    else:
        section_list = ["summary", "trend", "transactions", "categories", "payments"]

    timezone = normalize_timezone(timezone)
    from_date = parse_optional_datetime(from_param)
    to_date = parse_optional_datetime(to_param)
    current = revenue_service.resolve_range(range, timezone, from_date, to_date)
    summary = await revenue_service.get_summary(db, current)
    trend = await revenue_service.get_trend(db, current, "month", timezone)
    categories = await revenue_service.get_categories(db, current)
    payment_rows = await revenue_service.get_payment_methods(db, current)
    total = sum((row["amount"] for row in payment_rows), Decimal("0"))
    payments = []
    for row in payment_rows:
        pct = (row["amount"] / total * Decimal("100")) if total else Decimal("0")
        payments.append(
            {
                "name": row["method"].replace("_", " ").title(),
                "value": pct.quantize(Decimal("1")),
                "amount": row["amount"],
            }
        )
    transactions = await revenue_service.get_transactions(db, current, None, 50)

    import csv
    import io
    from starlette.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)

    if "summary" in section_list:
        writer.writerow(["Summary"])
        writer.writerow(["Revenue", "Expenses", "Profit"])
        writer.writerow([
            summary["totals"]["revenue"],
            summary["totals"]["expenses"],
            summary["totals"]["profit"],
        ])
        writer.writerow([])

    if "trend" in section_list:
        writer.writerow(["Trend"])
        writer.writerow(["Period", "Revenue", "Expenses", "Profit"])
        for row in trend:
            writer.writerow([row["period"], row["revenue"], row["expenses"], row["revenue"] - row["expenses"]])
        writer.writerow([])

    if "categories" in section_list:
        writer.writerow(["Categories"])
        writer.writerow(["Category", "Revenue"])
        for row in categories:
            writer.writerow([row["category"], row["revenue"]])
        writer.writerow([])

    if "payments" in section_list:
        writer.writerow(["Payments"])
        writer.writerow(["Name", "Value", "Amount"])
        for row in payments:
            writer.writerow([row["name"], row["value"], row["amount"]])
        writer.writerow([])

    if "transactions" in section_list:
        writer.writerow(["Transactions"])
        writer.writerow(["ID", "Customer", "Amount", "Time", "Status"])
        for row in transactions:
            writer.writerow([row["id"], row["customer"], row["amount"], row["time"], row["status"]])

    output.seek(0)
    filename = f"revenue_export_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
