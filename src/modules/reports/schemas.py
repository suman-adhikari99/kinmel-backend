"""
Reports Schemas
---------------
Pydantic models for reports endpoints.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


ReportId = Literal["sales", "orders", "inventory", "xero"]
ReportFormat = Literal["CSV", "PDF", "XLSX"]
ReportExportStatus = Literal["processing", "ready", "failed"]


class ReportSummaryResponse(BaseModel):
    period_label: str
    total_sales: Decimal
    total_orders: int
    growth_pct: float
    gst_collected: Decimal


class ReportTypeItem(BaseModel):
    id: ReportId
    name: str
    description: str
    formats: list[ReportFormat]
    last_generated_at: datetime | None


class ReportTypesResponse(BaseModel):
    items: list[ReportTypeItem]


class ReportExportCreateRequest(BaseModel):
    report_id: ReportId
    format: ReportFormat
    start_date: str
    end_date: str
    timezone: str | None = None


class ReportExportCreateResponse(BaseModel):
    id: str
    status: ReportExportStatus
    download_url: str | None = None


class ReportXeroExportRequest(BaseModel):
    start_date: str
    end_date: str
    timezone: str | None = None


class ReportExportItem(BaseModel):
    id: str
    name: str
    report_id: ReportId
    format: ReportFormat
    status: ReportExportStatus
    created_at: datetime
    size_kb: int | None
    download_url: str | None


class ReportExportListResponse(BaseModel):
    items: list[ReportExportItem]
    total: int


class ReportExportStatusResponse(BaseModel):
    id: str
    status: ReportExportStatus
    download_url: str | None = None
