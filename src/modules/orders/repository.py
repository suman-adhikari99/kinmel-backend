"""
Order Repository
----------------
Data access layer for order operations.
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.logging import LoggerMixin
from src.modules.orders.models import (
    Order,
    OrderExportJob,
    OrderExportStatus,
    OrderItem,
    OrderItemSubstitution,
    OrderStatusHistory,
)


class OrderRepository(LoggerMixin):
    """Repository for order data access."""

    def _base_query(self):
        return (
            select(Order)
            .options(
                selectinload(Order.items).selectinload(OrderItem.substitution),
            )
        )

    async def get_by_id(
        self,
        session: AsyncSession,
        order_id: str,
        *,
        include_history: bool = False,
    ) -> Order | None:
        """Get order by ID with items and substitutions."""
        query = self._base_query().where(Order.id == order_id)

        if include_history:
            query = query.options(selectinload(Order.status_history))

        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def list_orders(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        order_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
        customer_name: str | None = None,
        ordering_field: str = "created_at",
        ordering_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Order], int]:
        """List orders with optional filters and total count."""
        if ordering_field == "created_at":
            ordering_col = Order.created_at
        else:
            ordering_col = Order.created_at
        query = self._base_query().order_by(
            ordering_col.desc() if ordering_desc else ordering_col.asc()
        )

        if status:
            query = query.where(Order.status == status)
        if order_type:
            query = query.where(Order.order_type == order_type)
        if start_date:
            query = query.where(Order.created_at >= start_date)
        if end_date:
            query = query.where(Order.created_at <= end_date)
        if customer_name:
            query = query.where(Order.customer_name.ilike(f"%{customer_name}%"))
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    cast(Order.id, String).ilike(pattern),
                    Order.customer_name.ilike(pattern),
                    Order.customer_phone.ilike(pattern),
                    Order.customer_email.ilike(pattern),
                )
            )

        total_query = select(func.count()).select_from(query.subquery())
        total_result = await session.execute(total_query)
        total = int(total_result.scalar_one())

        result = await session.execute(query.limit(limit).offset(offset))
        return result.scalars().all(), total

    async def get_item(
        self,
        session: AsyncSession,
        order_id: str,
        item_id: str,
    ) -> OrderItem | None:
        """Get order item by ID within an order."""
        query = (
            select(OrderItem)
            .where(
                OrderItem.order_id == order_id,
                OrderItem.id == item_id,
            )
            .options(selectinload(OrderItem.substitution))
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def get_item_by_identifier(
        self,
        session: AsyncSession,
        order_id: str,
        identifier: str,
    ) -> OrderItem | None:
        """Get order item by ID or product SKU within an order."""
        query = (
            select(OrderItem)
            .where(
                OrderItem.order_id == order_id,
                or_(
                    OrderItem.id == identifier,
                    OrderItem.product_sku == identifier,
                ),
            )
            .options(selectinload(OrderItem.substitution))
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def add_status_history(
        self,
        session: AsyncSession,
        order_id: str,
        status: str,
        changed_by: str | None,
    ) -> OrderStatusHistory:
        """Insert status history entry."""
        entry = OrderStatusHistory(
            order_id=order_id,
            status=status,
            changed_by=changed_by,
        )
        session.add(entry)
        await session.flush()
        return entry

    async def get_status_counts(self, session: AsyncSession) -> dict[str, int]:
        """Get counts for each order status."""
        result = await session.execute(
            select(Order.status, func.count()).group_by(Order.status)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def export_orders_csv(
        self,
        session: AsyncSession,
        *,
        status: str | None = None,
        order_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        """Return flat order rows for CSV export."""
        query = (
            select(Order, OrderItem, OrderItemSubstitution)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .outerjoin(
                OrderItemSubstitution,
                OrderItemSubstitution.order_item_id == OrderItem.id,
            )
            .order_by(Order.created_at.desc(), OrderItem.created_at.desc())
        )

        if status:
            query = query.where(Order.status == status)
        if order_type:
            query = query.where(Order.order_type == order_type)
        if start_date:
            query = query.where(Order.created_at >= start_date)
        if end_date:
            query = query.where(Order.created_at <= end_date)
        if search:
            pattern = f"%{search}%"
            query = query.where(
                or_(
                    cast(Order.id, String).ilike(pattern),
                    Order.customer_name.ilike(pattern),
                    Order.customer_phone.ilike(pattern),
                    Order.customer_email.ilike(pattern),
                )
            )

        result = await session.execute(query.limit(limit).offset(offset))
        rows = []
        for order, item, substitution in result.all():
            rows.append(
                {
                    "order_id": str(order.id),
                    "created_at": order.created_at.isoformat() if order.created_at else "",
                    "status": order.status,
                    "type": order.order_type,
                    "time_slot": order.time_slot or "",
                    "customer_name": order.customer_name,
                    "customer_phone": order.customer_phone,
                    "customer_email": order.customer_email or "",
                    "delivery_address": order.delivery_address or "",
                    "delivery_suburb": order.delivery_suburb or "",
                    "subtotal": str(order.subtotal),
                    "gst": str(order.gst),
                    "delivery_fee": str(order.delivery_fee),
                    "total": str(order.total),
                    "notes": order.notes or "",
                    "item_id": str(item.id),
                    "item_sku": item.product_sku or "",
                    "item_name": item.name,
                    "item_quantity": str(item.quantity),
                    "item_price": str(item.price),
                    "item_checked": str(item.checked),
                    "substitution_status": substitution.status if substitution else "",
                    "substitution_reason": substitution.reason if substitution else "",
                    "substitute_item_id": substitution.substitute_item_id if substitution else "",
                    "substitute_name": substitution.substitute_name if substitution else "",
                    "substitute_price": str(substitution.substitute_price) if substitution else "",
                    "substitution_qty": str(substitution.quantity) if substitution else "",
                }
            )
        return rows

    async def create_export_job(
        self,
        session: AsyncSession,
        *,
        requested_by: str,
        destination_email: str,
        filters_json: str,
    ) -> OrderExportJob:
        """Create a new export job record."""
        job = OrderExportJob(
            requested_by=requested_by,
            destination_email=destination_email,
            status=OrderExportStatus.PENDING,
            filters_json=filters_json,
        )
        session.add(job)
        await session.flush()
        return job

    async def get_export_job(
        self,
        session: AsyncSession,
        job_id: str,
    ) -> OrderExportJob | None:
        """Fetch export job by ID."""
        result = await session.execute(
            select(OrderExportJob).where(OrderExportJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def update_export_job(
        self,
        session: AsyncSession,
        job_id: str,
        *,
        status: OrderExportStatus | None = None,
        file_url: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update export job status."""
        job = await self.get_export_job(session, job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if file_url is not None:
            job.file_url = file_url
        if error_message is not None:
            job.error_message = error_message
        await session.flush()

    async def upsert_substitution(
        self,
        session: AsyncSession,
        order_item: OrderItem,
        **kwargs,
    ) -> OrderItemSubstitution:
        """Create or update substitution for an order item."""
        substitution = order_item.substitution
        if substitution:
            for field, value in kwargs.items():
                setattr(substitution, field, value)
            await session.flush()
            return substitution

        substitution = OrderItemSubstitution(order_item_id=order_item.id, **kwargs)
        session.add(substitution)
        await session.flush()
        return substitution


# Singleton instance
order_repository = OrderRepository()
