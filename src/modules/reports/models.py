"""
Reports Models
--------------
Database models for report exports.
"""

from enum import StrEnum
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from src.core.models import BaseModel


class ReportFormat(StrEnum):
    CSV = "CSV"
    PDF = "PDF"
    XLSX = "XLSX"


class ReportExportStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ReportExport(BaseModel):
    __tablename__ = "report_exports"

    __table_args__ = (
        Index("ix_report_exports_report_id", "report_id"),
        Index("ix_report_exports_status", "status"),
    )

    report_id: Mapped[str] = mapped_column(String(50), nullable=False)
    format: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReportExportStatus.PROCESSING)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    size_kb: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
