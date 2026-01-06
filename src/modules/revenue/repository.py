"""
Revenue Repository
------------------
Database queries for revenue analytics.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import String, cast, func, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.orders.models import Order, OrderItem
from src.modules.products.models import Product
from src.modules.revenue.models import (
    AdjustmentType,
    BusinessProfile,
    PaymentMethod,
    PaymentStatus,
    PayoutStatus,
    RevenueAdjustment,
    RevenuePayment,
    RevenuePayout,
)


class RevenueRepository:
    """Queries for revenue analytics."""

    def _is_missing_table(self, exc: Exception) -> bool:
        if not isinstance(exc, ProgrammingError):
            return False
        try:
            from asyncpg.exceptions import UndefinedTableError
        except Exception:
            UndefinedTableError = None
        if UndefinedTableError and isinstance(exc.orig, UndefinedTableError):
            return True
        return "UndefinedTableError" in str(exc.orig)

    async def get_totals(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[str, Decimal]:
        revenue_query = select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
        )
        revenue_result = await session.execute(revenue_query)
        revenue = Decimal(str(revenue_result.scalar() or 0))

        expenses_query = (
            select(
                func.coalesce(func.sum(OrderItem.quantity * Product.cost_price), 0)
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Product, Product.sku == OrderItem.product_sku)
            .where(
                Order.created_at >= start_date,
                Order.created_at <= end_date,
            )
        )
        expenses_result = await session.execute(expenses_query)
        expenses = Decimal(str(expenses_result.scalar() or 0))

        return {
            "revenue": revenue,
            "expenses": expenses,
            "profit": revenue - expenses,
        }

    async def get_trend(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
        interval: str,
        timezone: str,
    ) -> list[dict]:
        tz_timestamp = func.timezone(timezone, Order.created_at)
        period = func.date_trunc(interval, tz_timestamp).label("period")
        revenue_query = (
            select(
                period,
                func.coalesce(func.sum(Order.total), 0).label("revenue"),
            )
            .select_from(Order)
            .where(Order.created_at >= start_date, Order.created_at <= end_date)
            .group_by(period)
            .order_by(period)
        )
        revenue_result = await session.execute(revenue_query)
        revenue_rows = {
            row.period: Decimal(str(row.revenue or 0)) for row in revenue_result.all()
        }

        expense_query = (
            select(
                period,
                func.coalesce(
                    func.sum(OrderItem.quantity * Product.cost_price), 0
                ).label("expenses"),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Product, Product.sku == OrderItem.product_sku)
            .where(Order.created_at >= start_date, Order.created_at <= end_date)
            .group_by(period)
            .order_by(period)
        )
        expense_result = await session.execute(expense_query)
        expense_rows = {
            row.period: Decimal(str(row.expenses or 0)) for row in expense_result.all()
        }

        periods = sorted(set(revenue_rows.keys()) | set(expense_rows.keys()))
        rows = []
        for period_value in periods:
            rows.append(
                {
                    "period": period_value,
                    "revenue": revenue_rows.get(period_value, Decimal("0")),
                    "expenses": expense_rows.get(period_value, Decimal("0")),
                }
            )
        return rows

    async def get_daily_by_type(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
        timezone: str,
        types: list[str] | None = None,
    ) -> list[dict]:
        tz_timestamp = func.timezone(timezone, Order.created_at)
        period = func.date_trunc("day", tz_timestamp).label("period")
        query = (
            select(
                period,
                Order.order_type.label("order_type"),
                func.coalesce(func.sum(Order.total), 0).label("revenue"),
            )
            .where(Order.created_at >= start_date, Order.created_at <= end_date)
            .group_by(period, Order.order_type)
            .order_by(period)
        )
        if types:
            query = query.where(Order.order_type.in_(types))
        result = await session.execute(query)
        return [
            {
                "period": row.period,
                "order_type": row.order_type,
                "revenue": Decimal(str(row.revenue or 0)),
            }
            for row in result.all()
        ]

    async def get_categories(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        query = (
            select(
                Product.category,
                func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).label(
                    "revenue"
                ),
            )
            .select_from(OrderItem)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(Product, Product.sku == OrderItem.product_sku)
            .where(Order.created_at >= start_date, Order.created_at <= end_date)
            .group_by(Product.category)
            .order_by(func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0).desc())
        )
        result = await session.execute(query)
        rows = []
        for row in result.all():
            category = row.category.value if hasattr(row.category, "value") else str(row.category)
            rows.append({"category": category, "revenue": Decimal(str(row.revenue or 0))})
        return rows

    async def get_transactions(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
        status: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        query = (
            select(
                cast(Order.id, String).label("id"),
                Order.customer_name,
                Order.total,
                Order.created_at,
                Order.status,
            )
            .where(Order.created_at >= start_date, Order.created_at <= end_date)
            .order_by(Order.created_at.desc())
            .limit(limit)
        )
        if status:
            query = query.where(Order.status == status)
        result = await session.execute(query)
        return [
            {
                "id": row.id,
                "customer": row.customer_name,
                "amount": Decimal(str(row.total or 0)),
                "time": row.created_at,
                "status": row.status,
            }
            for row in result.all()
        ]

    async def get_payment_methods(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        try:
            query = (
                select(RevenuePayment.method, func.coalesce(func.sum(RevenuePayment.amount), 0))
                .where(
                    RevenuePayment.created_at >= start_date,
                    RevenuePayment.created_at <= end_date,
                    RevenuePayment.status == PaymentStatus.COMPLETED,
                )
                .group_by(RevenuePayment.method)
            )
            result = await session.execute(query)
            return [
                {
                    "method": row[0],
                    "amount": Decimal(str(row[1] or 0)),
                }
                for row in result.all()
            ]
        except ProgrammingError as exc:
            if self._is_missing_table(exc):
                return []
            raise

    async def get_payout_summary(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        try:
            next_payout_query = (
                select(RevenuePayout.payout_at)
                .where(RevenuePayout.status == PayoutStatus.PENDING)
                .order_by(RevenuePayout.payout_at.asc())
                .limit(1)
            )
            last_payout_query = (
                select(RevenuePayout.payout_at)
                .where(RevenuePayout.status == PayoutStatus.COMPLETED)
                .order_by(RevenuePayout.payout_at.desc())
                .limit(1)
            )
            pending_amount_query = select(func.coalesce(func.sum(RevenuePayout.amount), 0)).where(
                RevenuePayout.status == PayoutStatus.PENDING
            )
            completed_count_query = select(func.count(RevenuePayout.id)).where(
                RevenuePayout.status == PayoutStatus.COMPLETED,
                RevenuePayout.created_at >= start_date,
                RevenuePayout.created_at <= end_date,
            )
            profile_query = select(BusinessProfile).limit(1)

            next_payout = (await session.execute(next_payout_query)).scalar_one_or_none()
            last_payout = (await session.execute(last_payout_query)).scalar_one_or_none()
            pending_amount = Decimal(str((await session.execute(pending_amount_query)).scalar() or 0))
            completed_count = int((await session.execute(completed_count_query)).scalar() or 0)
            profile = (await session.execute(profile_query)).scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_table(exc):
                return {
                    "next_payout": None,
                    "last_payout": None,
                    "pending_amount": Decimal("0"),
                    "completed_count": 0,
                    "payout_frequency": "Daily",
                    "processor": "Stripe",
                }
            raise

        return {
            "next_payout": next_payout,
            "last_payout": last_payout,
            "pending_amount": pending_amount,
            "completed_count": completed_count,
            "payout_frequency": profile.payout_frequency if profile else "Daily",
            "processor": profile.processor if profile else "Stripe",
        }

    async def get_adjustments(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> dict:
        try:
            platform_fees_query = select(func.coalesce(func.sum(RevenueAdjustment.amount), 0)).where(
                RevenueAdjustment.adjustment_type == AdjustmentType.PLATFORM_FEE,
                RevenueAdjustment.created_at >= start_date,
                RevenueAdjustment.created_at <= end_date,
            )
            refunds_query = select(func.coalesce(func.sum(RevenueAdjustment.amount), 0)).where(
                RevenueAdjustment.adjustment_type == AdjustmentType.REFUND,
                RevenueAdjustment.created_at >= start_date,
                RevenueAdjustment.created_at <= end_date,
            )
            disputes_query = select(func.coalesce(func.sum(RevenueAdjustment.amount), 0)).where(
                RevenueAdjustment.adjustment_type == AdjustmentType.DISPUTE,
                RevenueAdjustment.created_at >= start_date,
                RevenueAdjustment.created_at <= end_date,
            )

            platform_fees = Decimal(str((await session.execute(platform_fees_query)).scalar() or 0))
            refunds = Decimal(str((await session.execute(refunds_query)).scalar() or 0))
            disputes = Decimal(str((await session.execute(disputes_query)).scalar() or 0))
        except ProgrammingError as exc:
            if self._is_missing_table(exc):
                return {
                    "platform_fees": Decimal("0"),
                    "refunds": Decimal("0"),
                    "disputes": Decimal("0"),
                }
            raise

        return {
            "platform_fees": platform_fees,
            "refunds": refunds,
            "disputes": disputes,
        }

    async def get_business_profile(self, session: AsyncSession) -> BusinessProfile | None:
        try:
            result = await session.execute(select(BusinessProfile).limit(1))
            return result.scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_table(exc):
                return None
            raise

    async def get_gst_total(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> Decimal:
        query = select(func.coalesce(func.sum(Order.gst), 0)).where(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
        )
        result = await session.execute(query)
        return Decimal(str(result.scalar() or 0))

    async def get_pending_amount(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> Decimal:
        query = select(func.coalesce(func.sum(Order.total), 0)).where(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
            Order.status.in_(["preparing", "ready", "out_for_delivery"]),
        )
        result = await session.execute(query)
        return Decimal(str(result.scalar() or 0))

    async def count_completed_in_month(
        self,
        session: AsyncSession,
        *,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        query = select(func.count(Order.id)).where(
            Order.created_at >= start_date,
            Order.created_at <= end_date,
            Order.status == "completed",
        )
        result = await session.execute(query)
        return int(result.scalar() or 0)


revenue_repository = RevenueRepository()
