"""
Revenue Service
---------------
Business logic for revenue analytics.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from src.core.exceptions import ValidationError
from src.modules.revenue.repository import revenue_repository


@dataclass
class RevenueRange:
    start: datetime
    end: datetime
    range_label: str


class RevenueService:
    """Service for revenue analytics."""

    def parse_timezone(self, timezone: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone)
        except Exception as exc:
            raise ValidationError("timezone", "Invalid timezone") from exc

    def resolve_range(
        self,
        range_value: str,
        timezone: str,
        start_date: datetime | None,
        end_date: datetime | None,
    ) -> RevenueRange:
        tz = self.parse_timezone(timezone)
        now = datetime.now(tz)

        if range_value == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif range_value == "week":
            start = (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            end = now
        elif range_value == "month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif range_value == "year":
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now
        elif range_value == "custom":
            if not start_date or not end_date:
                raise ValidationError("range", "from and to are required for custom range")
            start = start_date.astimezone(tz) if start_date.tzinfo else start_date.replace(tzinfo=tz)
            end = end_date.astimezone(tz) if end_date.tzinfo else end_date.replace(tzinfo=tz)
        else:
            raise ValidationError("range", "Invalid range value")

        if start > end:
            raise ValidationError("range", "from must be before to")

        return RevenueRange(start=start.astimezone(UTC), end=end.astimezone(UTC), range_label=range_value)

    def previous_range(self, current: RevenueRange) -> RevenueRange:
        duration = current.end - current.start
        prev_end = current.start
        prev_start = current.start - duration
        return RevenueRange(start=prev_start, end=prev_end, range_label=current.range_label)

    async def get_summary(self, session, current: RevenueRange) -> dict:
        totals = await revenue_repository.get_totals(
            session,
            start_date=current.start,
            end_date=current.end,
        )
        prev = self.previous_range(current)
        prev_totals = await revenue_repository.get_totals(
            session,
            start_date=prev.start,
            end_date=prev.end,
        )

        def pct_change(current_value: Decimal, prev_value: Decimal) -> Decimal:
            if prev_value == 0:
                return Decimal("0")
            return ((current_value - prev_value) / prev_value * Decimal("100")).quantize(Decimal("0.1"))

        comparisons = {
            "revenueChangePct": pct_change(totals["revenue"], prev_totals["revenue"]),
            "expensesChangePct": pct_change(totals["expenses"], prev_totals["expenses"]),
            "profitChangePct": pct_change(totals["profit"], prev_totals["profit"]),
        }

        return {"totals": totals, "comparisons": comparisons}

    async def get_trend(self, session, current: RevenueRange, interval: str, timezone: str) -> list[dict]:
        return await revenue_repository.get_trend(
            session,
            start_date=current.start,
            end_date=current.end,
            interval=interval,
            timezone=timezone,
        )

    async def get_daily_by_type(
        self,
        session,
        current: RevenueRange,
        timezone: str,
        types: list[str] | None,
    ) -> list[dict]:
        return await revenue_repository.get_daily_by_type(
            session,
            start_date=current.start,
            end_date=current.end,
            timezone=timezone,
            types=types,
        )

    async def get_categories(self, session, current: RevenueRange) -> list[dict]:
        return await revenue_repository.get_categories(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_transactions(
        self,
        session,
        current: RevenueRange,
        status: str | None,
        limit: int,
    ) -> list[dict]:
        return await revenue_repository.get_transactions(
            session,
            start_date=current.start,
            end_date=current.end,
            status=status,
            limit=limit,
        )

    async def get_gst_total(self, session, current: RevenueRange) -> Decimal:
        return await revenue_repository.get_gst_total(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_pending_amount(self, session, current: RevenueRange) -> Decimal:
        return await revenue_repository.get_pending_amount(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def count_completed(self, session, current: RevenueRange) -> int:
        return await revenue_repository.count_completed_in_month(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_payment_methods(self, session, current: RevenueRange) -> list[dict]:
        return await revenue_repository.get_payment_methods(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_payout_summary(self, session, current: RevenueRange) -> dict:
        return await revenue_repository.get_payout_summary(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_adjustments(self, session, current: RevenueRange) -> dict:
        return await revenue_repository.get_adjustments(
            session,
            start_date=current.start,
            end_date=current.end,
        )

    async def get_business_profile(self, session):
        return await revenue_repository.get_business_profile(session)


revenue_service = RevenueService()
