"""
Order Export Tasks
------------------
Background tasks for order exports.
"""

import csv
import io
from datetime import UTC, datetime

from src.core.email import get_email_service
from src.core.logging import get_logger
from src.tasks.base import BaseTask, run_async
from src.tasks.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    base=BaseTask,
    bind=True,
    name="src.tasks.order_tasks.export_orders_email",
    max_retries=3,
    default_retry_delay=300,
)
def export_orders_email(
    self,
    job_id: str,
    to_email: str,
    filters: dict,
) -> dict:
    """Export orders and send CSV via email."""
    return run_async(_export_orders_email_async(job_id, to_email, filters))


async def _export_orders_email_async(job_id: str, to_email: str, filters: dict) -> dict:
    from src.core.database import async_session_factory
    from src.modules.orders.repository import order_repository
    from src.modules.orders.models import OrderExportStatus

    def _parse_dt(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None

    start_date = _parse_dt(filters.get("start_date"))
    end_date = _parse_dt(filters.get("end_date"))

    async with async_session_factory() as session:
        await order_repository.update_export_job(
            session,
            job_id,
            status=OrderExportStatus.PROCESSING,
        )
        rows = await order_repository.export_orders_csv(
            session,
            status=filters.get("status"),
            order_type=filters.get("order_type"),
            start_date=start_date,
            end_date=end_date,
            search=filters.get("search"),
            limit=filters.get("limit", 100000),
            offset=filters.get("offset", 0),
        )

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

    csv_bytes = output.getvalue().encode("utf-8")

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"orders_export_{timestamp}.csv"

    email_service = get_email_service()
    if not email_service.is_configured():
        logger.warning("Email service not configured; skipping export email")
        async with async_session_factory() as session:
            await order_repository.update_export_job(
                session,
                job_id,
                status=OrderExportStatus.FAILED,
                error_message="Email service not configured",
            )
        return {"status": "failed", "reason": "email_not_configured"}

    subject = "Orders Export - Kinmel"
    html_body = """
    <p>Your orders export is ready.</p>
    <p>The CSV is attached.</p>
    """
    text_body = "Your orders export is ready. The CSV is attached."

    sent = email_service.send_email_with_attachment(
        to_email,
        subject,
        html_body,
        text_body,
        filename=filename,
        content=csv_bytes,
        mime_type="text/csv",
    )

    async with async_session_factory() as session:
        await order_repository.update_export_job(
            session,
            job_id,
            status=OrderExportStatus.DONE if sent else OrderExportStatus.FAILED,
            error_message=None if sent else "Failed to send email",
        )

    return {"status": "sent" if sent else "failed", "filename": filename}
