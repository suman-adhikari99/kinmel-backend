"""
Reports Repository
------------------
Data access for report exports.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.modules.reports.models import ReportExport


class ReportsRepository:
    async def create_export(
        self,
        session: AsyncSession,
        *,
        report_id: str,
        format: str,
        status: str,
    ) -> ReportExport:
        export = ReportExport(
            report_id=report_id,
            format=format,
            status=status,
        )
        session.add(export)
        await session.flush()
        return export

    async def update_export(
        self,
        session: AsyncSession,
        export: ReportExport,
        *,
        status: str,
        file_path: str | None = None,
        size_kb: int | None = None,
        error_message: str | None = None,
    ) -> ReportExport:
        export.status = status
        export.file_path = file_path
        export.size_kb = size_kb
        export.error_message = error_message
        await session.flush()
        return export

    async def get_export(
        self,
        session: AsyncSession,
        export_id: str,
    ) -> ReportExport | None:
        result = await session.execute(
            select(ReportExport).where(ReportExport.id == export_id)
        )
        return result.scalar_one_or_none()

    async def list_exports(
        self,
        session: AsyncSession,
        *,
        report_id: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ReportExport], int]:
        query = select(ReportExport)
        count_query = select(func.count()).select_from(ReportExport)
        if report_id:
            query = query.where(ReportExport.report_id == report_id)
            count_query = count_query.where(ReportExport.report_id == report_id)
        if status:
            query = query.where(ReportExport.status == status)
            count_query = count_query.where(ReportExport.status == status)
        query = query.order_by(ReportExport.created_at.desc())
        total = (await session.execute(count_query)).scalar_one()
        result = await session.execute(query.limit(limit).offset(offset))
        return result.scalars().all(), int(total)

    async def get_last_generated_at(
        self,
        session: AsyncSession,
        report_id: str,
    ):
        result = await session.execute(
            select(func.max(ReportExport.created_at)).where(
                ReportExport.report_id == report_id,
                ReportExport.status == "ready",
            )
        )
        return result.scalar_one_or_none()


reports_repository = ReportsRepository()
