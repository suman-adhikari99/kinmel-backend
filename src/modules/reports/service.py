"""
Reports Service
---------------
Business logic for reports.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ValidationError
from src.modules.orders.models import Order
from src.modules.reports.models import ReportExportStatus
from src.modules.reports.repository import reports_repository


EXPORT_DIR = Path("uploads/reports")


def _parse_dates(start_date: str, end_date: str, timezone: str | None) -> tuple[datetime, datetime]:
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("date", "Invalid date format (YYYY-MM-DD)") from exc
    if start > end:
        raise ValidationError("date", "start_date must be before or equal to end_date")

    tz = ZoneInfo(timezone) if timezone else ZoneInfo("UTC")
    start_dt = datetime.combine(start, time.min, tzinfo=tz).astimezone(UTC)
    end_dt = datetime.combine(end, time.max, tzinfo=tz).astimezone(UTC)
    return start_dt, end_dt


def _normalize_bucket_value(value: Any) -> str:
    """Convert grouped date bucket values into ISO strings."""
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _period_label(start_dt: datetime, end_dt: datetime) -> str:
    now = datetime.now(UTC).date()
    if start_dt.date().replace(day=1) == now.replace(day=1) and end_dt.date() >= now:
        return "This month"
    return "Custom"


class ReportsService:
    async def get_summary(
        self,
        session: AsyncSession,
        *,
        start_date: str,
        end_date: str,
        timezone: str | None,
    ) -> dict:
        start_dt, end_dt = _parse_dates(start_date, end_date, timezone)
        period_label = _period_label(start_dt, end_dt)

        totals = await session.execute(
            select(
                func.coalesce(func.sum(Order.total), 0),
                func.count(Order.id),
                func.coalesce(func.sum(Order.gst), 0),
            ).where(Order.created_at >= start_dt, Order.created_at <= end_dt)
        )
        total_sales, total_orders, gst_collected = totals.one()

        period_days = (end_dt.date() - start_dt.date()).days + 1
        prev_end = start_dt - timedelta(seconds=1)
        prev_start = prev_end - timedelta(days=period_days - 1)
        prev_totals = await session.execute(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.created_at >= prev_start,
                Order.created_at <= prev_end,
            )
        )
        prev_sales = Decimal(prev_totals.scalar_one() or 0)
        growth_pct = 0.0
        if prev_sales > 0:
            growth_pct = float(((Decimal(total_sales) - prev_sales) / prev_sales) * 100)

        return {
            "period_label": period_label,
            "total_sales": Decimal(total_sales),
            "total_orders": int(total_orders),
            "growth_pct": round(growth_pct, 2),
            "gst_collected": Decimal(gst_collected),
        }

    async def get_report_types(self, session: AsyncSession) -> list[dict]:
        sales_last = await reports_repository.get_last_generated_at(session, "sales")
        orders_last = await reports_repository.get_last_generated_at(session, "orders")
        xero_last = await reports_repository.get_last_generated_at(session, "xero")
        return [
            {
                "id": "sales",
                "name": "Sales Report",
                "description": "Daily, weekly, or monthly sales summary with GST breakdown",
                "formats": ["CSV", "PDF", "XLSX"],
                "last_generated_at": sales_last,
            },
            {
                "id": "orders",
                "name": "Orders Report",
                "description": "Complete order history with customer details and status",
                "formats": ["CSV", "PDF"],
                "last_generated_at": orders_last,
            },
            {
                "id": "xero",
                "name": "Xero Export",
                "description": "Xero-compatible CSV export for accounting import",
                "formats": ["CSV"],
                "last_generated_at": xero_last,
            },
        ]

    async def create_export(
        self,
        session: AsyncSession,
        *,
        report_id: str,
        format: str,
        start_date: str,
        end_date: str,
        timezone: str | None,
    ) -> dict:
        if report_id == "xero" and format != "CSV":
            raise ValidationError("format", "Xero export only supports CSV")
        export = await reports_repository.create_export(
            session,
            report_id=report_id,
            format=format,
            status=ReportExportStatus.PROCESSING,
        )
        await session.flush()

        try:
            async with session.begin_nested():
                file_path, size_kb = await self._generate_export_file(
                    session=session,
                    report_id=report_id,
                    format=format,
                    start_date=start_date,
                    end_date=end_date,
                    timezone=timezone,
                    export_id=export.id,
                )
                await reports_repository.update_export(
                    session,
                    export,
                    status=ReportExportStatus.READY,
                    file_path=file_path,
                    size_kb=size_kb,
                )
                return {"export": export, "ready": True}
        except Exception as exc:
            await reports_repository.update_export(
                session,
                export,
                status=ReportExportStatus.FAILED,
                error_message=str(exc),
            )
            return {"export": export, "ready": False}

    async def _generate_export_file(
        self,
        *,
        session: AsyncSession,
        report_id: str,
        format: str,
        start_date: str,
        end_date: str,
        timezone: str | None,
        export_id: str,
    ) -> tuple[str, int]:
        start_dt, end_dt = _parse_dates(start_date, end_date, timezone)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)

        rows = await self._fetch_rows(session, report_id, start_dt, end_dt)
        filename = f"{report_id}_report_{export_id}.{format.lower()}"
        file_path = EXPORT_DIR / filename

        if format == "CSV":
            size_kb = _write_csv(file_path, rows)
        elif format == "XLSX":
            size_kb = _write_xlsx(file_path, rows)
        elif format == "PDF":
            size_kb = _write_pdf(file_path, rows, title=f"{report_id.title()} Report")
        else:
            raise ValidationError("format", "Unsupported report format")

        return str(file_path), size_kb

    async def _fetch_rows(
        self,
        session: AsyncSession,
        report_id: str,
        start_dt: datetime,
        end_dt: datetime,
    ) -> Iterable[dict]:
        if report_id in {"sales", "xero"}:
            date_bucket = func.strftime("%Y-%m-%d", Order.created_at).label("date_bucket")
            result = await session.execute(
                select(
                    date_bucket,
                    func.coalesce(func.sum(Order.total), 0).label("total_sales"),
                    func.coalesce(func.sum(Order.gst), 0).label("gst"),
                    func.count(Order.id).label("orders"),
                )
                .where(Order.created_at >= start_dt, Order.created_at <= end_dt)
                .group_by(date_bucket)
                .order_by(date_bucket)
            )
            rows = []
            for row in result:
                date_str = _normalize_bucket_value(row.date_bucket)
                rows.append(
                    {
                        "date": date_str,
                        "total_sales": float(row.total_sales or 0),
                        "gst": float(row.gst or 0),
                        "orders": int(row.orders or 0),
                    }
                )
            return rows
        if report_id == "orders":
            result = await session.execute(
                select(Order).where(Order.created_at >= start_dt, Order.created_at <= end_dt)
            )
            orders = result.scalars().all()
            return [
                {
                    "order_id": order.id,
                    "customer": order.customer_name,
                    "email": order.customer_email,
                    "status": order.status,
                    "total": float(order.total),
                    "gst": float(order.gst),
                    "created_at": order.created_at.isoformat(),
                }
                for order in orders
            ]
        raise ValidationError("report_id", "Unsupported report id")


def _write_csv(file_path: Path, rows: Iterable[dict]) -> int:
    import csv
    from io import StringIO

    rows = list(rows)
    buffer = StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("")
    file_path.write_text(buffer.getvalue(), encoding="utf-8")
    return max(1, int(file_path.stat().st_size / 1024))


def _write_xlsx(file_path: Path, rows: Iterable[dict]) -> int:
    from openpyxl import Workbook

    rows = list(rows)
    wb = Workbook()
    ws = wb.active
    if rows:
        ws.append(list(rows[0].keys()))
        for row in rows:
            ws.append(list(row.values()))
    wb.save(file_path)
    return max(1, int(file_path.stat().st_size / 1024))


def _write_pdf(file_path: Path, rows: Iterable[dict], *, title: str) -> int:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    rows = list(rows)
    c = canvas.Canvas(str(file_path), pagesize=letter)
    width, height = letter
    y = height - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, title)
    y -= 20
    c.setFont("Helvetica", 9)
    if rows:
        headers = list(rows[0].keys())
        c.drawString(40, y, " | ".join(headers))
        y -= 12
        for row in rows[:200]:
            line = " | ".join(str(row[h]) for h in headers)
            c.drawString(40, y, line[:120])
            y -= 12
            if y < 60:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 9)
    else:
        c.drawString(40, y, "No data")
    c.save()
    return max(1, int(file_path.stat().st_size / 1024))


reports_service = ReportsService()
