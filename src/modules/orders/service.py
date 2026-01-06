"""
Order Service
-------------
Business logic for order operations.
"""

from dataclasses import dataclass
import json
from uuid import UUID
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError, ValidationError
from src.core.logging import LoggerMixin
from src.modules.orders.models import (
    ContactChannel,
    Order,
    OrderContactAttempt,
    OrderExportStatus,
    OrderItem,
    OrderStatus,
    OrderType,
    SubstitutionStatus,
)
from src.modules.orders.repository import order_repository
from src.modules.products.repository import product_repository
from src.core.config import get_settings
from src.modules.notifications.repository import notifications_repository
from src.modules.notifications.service import notifications_service
from src.tasks.email_tasks import send_notification_email_task


@dataclass
class OrderListFilters:
    """Filters for listing orders."""

    status: OrderStatus | None = None
    order_type: OrderType | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    search: str | None = None
    customer_name: str | None = None
    ordering_field: str = "created_at"
    ordering_desc: bool = True
    limit: int = 50
    offset: int = 0


@dataclass
class SubstitutionInput:
    """Input data for a substitution."""

    original_item_id: str | None
    substitute_item_id: str | None
    quantity: Decimal
    reason: str
    status: SubstitutionStatus
    price_difference: Decimal | None = None
    customer_notified: bool | None = None


class OrderService(LoggerMixin):
    """Service layer for order operations."""

    def _send_admin_email(self, subject: str, message: str, source_href: str | None) -> None:
        settings = get_settings()
        if not settings.alert_email_recipients:
            return
        text_body = f"{subject}\n\n{message}"
        if source_href:
            text_body = f"{text_body}\n\nView: {source_href}"
        html_message = message.replace("\n", "<br>")
        html_body = f"<h3>{subject}</h3><p>{html_message}</p>"
        if source_href:
            html_body += f"<p><a href=\"{source_href}\">Open order</a></p>"
        send_notification_email_task.delay(
            settings.alert_email_recipients,
            subject,
            text_body,
            html_body,
        )

    async def list_orders(
        self,
        session: AsyncSession,
        filters: OrderListFilters,
    ) -> tuple[list[Order], int]:
        """List orders with pagination and search."""
        return await order_repository.list_orders(
            session,
            status=filters.status.value if filters.status else None,
            order_type=filters.order_type.value if filters.order_type else None,
            start_date=filters.start_date,
            end_date=filters.end_date,
            search=filters.search,
            customer_name=filters.customer_name,
            ordering_field=filters.ordering_field,
            ordering_desc=filters.ordering_desc,
            limit=filters.limit,
            offset=filters.offset,
        )

    async def get_status_summary(self, session: AsyncSession) -> dict[str, int]:
        """Get order counts per status and total."""
        counts = await order_repository.get_status_counts(session)
        summary = {
            "total": sum(counts.values()),
            "pending": counts.get(OrderStatus.NEW.value, 0),
            "preparing": counts.get(OrderStatus.PREPARING.value, 0),
            "ready": counts.get(OrderStatus.READY.value, 0),
            "out_for_delivery": counts.get(OrderStatus.OUT_FOR_DELIVERY.value, 0),
            "completed": counts.get(OrderStatus.COMPLETED.value, 0),
            "cancelled": counts.get(OrderStatus.CANCELLED.value, 0),
        }
        return summary

    async def export_orders_csv(
        self,
        session: AsyncSession,
        *,
        status: OrderStatus | None = None,
        order_type: OrderType | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        search: str | None = None,
        limit: int = 10000,
        offset: int = 0,
    ) -> list[dict[str, str]]:
        """Export orders as flat rows for CSV."""
        return await order_repository.export_orders_csv(
            session,
            status=status.value if status else None,
            order_type=order_type.value if order_type else None,
            start_date=start_date,
            end_date=end_date,
            search=search,
            limit=limit,
            offset=offset,
        )

    async def create_export_job(
        self,
        session: AsyncSession,
        *,
        requested_by: str,
        destination_email: str,
        filters: dict,
    ):
        """Create export job record."""
        return await order_repository.create_export_job(
            session,
            requested_by=requested_by,
            destination_email=destination_email,
            filters_json=json.dumps(filters),
        )

    async def get_export_job(self, session: AsyncSession, job_id: str):
        """Fetch export job by ID."""
        return await order_repository.get_export_job(session, job_id)

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
        await order_repository.update_export_job(
            session,
            job_id,
            status=status,
            file_url=file_url,
            error_message=error_message,
        )

    async def get_order(self, session: AsyncSession, order_id: str) -> Order:
        """Get order by ID with detail."""
        order = await order_repository.get_by_id(
            session,
            order_id,
            include_history=True,
        )
        if not order:
            raise NotFoundError("Order", order_id)
        return order

    async def update_status(
        self,
        session: AsyncSession,
        order_id: str,
        status: OrderStatus,
        user_id: str | None,
    ) -> Order:
        """Update order status and append history."""
        order = await order_repository.get_by_id(session, order_id, include_history=True)
        if not order:
            raise NotFoundError("Order", order_id)

        if order.status == status:
            if status == OrderStatus.CANCELLED:
                source_href = f"/dashboard/orders/{order.id}"
                title = f"Order Cancelled #{order.id}"
                already_sent = await notifications_repository.notification_exists(
                    session,
                    title=title,
                    source_href=source_href,
                )
                if not already_sent:
                    await notifications_service.create_notification(
                        session,
                        notif_type="alert",
                        title=title,
                        message=f"Order for {order.customer_name} was cancelled.",
                        source_label="View order",
                        source_href=source_href,
                    )
                    self._send_admin_email(
                        title,
                        f"Order for {order.customer_name} was cancelled.",
                        source_href,
                    )
            return order

        previous_status = order.status
        order.status = status
        if status == OrderStatus.COMPLETED:
            order.delivered_at = datetime.now(UTC)

        await order_repository.add_status_history(
            session,
            order_id=order.id,
            status=status,
            changed_by=user_id,
        )
        if status == OrderStatus.NEW and previous_status != OrderStatus.NEW:
            source_href = f"/dashboard/orders/{order.id}"
            await notifications_service.create_notification(
                session,
                notif_type="order",
                title=f"New Order #{order.id}",
                message=f"{order.order_type.value.title()} order from {order.customer_name}.",
                source_label="View order",
                source_href=source_href,
            )
            self._send_admin_email(
                f"New Order #{order.id}",
                f"{order.order_type.value.title()} order from {order.customer_name}.",
                source_href,
            )
        if status == OrderStatus.CANCELLED:
            source_href = f"/dashboard/orders/{order.id}"
            await notifications_service.create_notification(
                session,
                notif_type="alert",
                title=f"Order Cancelled #{order.id}",
                message=f"Order for {order.customer_name} was cancelled.",
                source_label="View order",
                source_href=source_href,
            )
            self._send_admin_email(
                f"Order Cancelled #{order.id}",
                f"Order for {order.customer_name} was cancelled.",
                source_href,
            )
        await session.flush()
        await session.refresh(order)
        return order

    async def update_item_checklist(
        self,
        session: AsyncSession,
        order_id: str,
        item_id: str,
        checked: bool,
    ) -> OrderItem:
        """Update checklist state for an order item."""
        item = await order_repository.get_item(session, order_id, item_id)
        if not item:
            raise NotFoundError("OrderItem", item_id)

        item.checked = checked
        await session.flush()
        return item

    async def create_substitution(
        self,
        session: AsyncSession,
        order_id: str,
        item_identifier: str | None,
        payload: SubstitutionInput,
    ) -> Order:
        """Create or update substitution for an order item."""
        order = await order_repository.get_by_id(session, order_id, include_history=True)
        if not order:
            raise NotFoundError("Order", order_id)

        if not item_identifier:
            raise ValidationError("original_item_id", "Original item identifier is required")

        item = await order_repository.get_item_by_identifier(
            session,
            order_id,
            item_identifier,
        )
        if not item:
            raise NotFoundError("OrderItem", item_identifier)

        if payload.quantity <= 0:
            raise ValidationError("quantity", "Quantity must be greater than 0")

        substitute_name = item.name
        substitute_price = item.price
        if payload.substitute_item_id:
            product = await product_repository.get_by_sku(
                session,
                payload.substitute_item_id,
            )
            if not product:
                try:
                    UUID(payload.substitute_item_id)
                except ValueError:
                    product = None
                else:
                    product = await product_repository.get_by_id(
                        session,
                        payload.substitute_item_id,
                    )
            if not product:
                raise ValidationError(
                    "substitute_item_id",
                    "Substitute item not found (SKU or ID)",
                )
            substitute_name = product.name
            substitute_price = product.unit_price

        await order_repository.upsert_substitution(
            session,
            item,
            original_item_id=payload.original_item_id or item.product_sku,
            original_name=item.name,
            original_price=item.price,
            original_qty=item.quantity,
            reason=payload.reason,
            price_difference=payload.price_difference,
            customer_notified=payload.customer_notified,
            status=payload.status,
            substitute_item_id=payload.substitute_item_id,
            substitute_name=substitute_name,
            substitute_price=substitute_price,
            quantity=payload.quantity,
        )

        order.has_substitutions = True
        await session.flush()
        return order

    async def log_contact_attempt(
        self,
        session: AsyncSession,
        order_id: str,
        channel: ContactChannel,
        template_id: str | None,
        notes: str | None,
    ) -> tuple[Order, OrderContactAttempt]:
        """Log a contact attempt for an order."""
        order = await order_repository.get_by_id(session, order_id, include_history=True)
        if not order:
            raise NotFoundError("Order", order_id)

        attempt = OrderContactAttempt(
            order_id=order.id,
            channel=channel,
            template_id=template_id,
            notes=notes,
        )
        session.add(attempt)
        await session.flush()
        await session.refresh(attempt)
        return order, attempt


# Singleton instance
order_service = OrderService()
