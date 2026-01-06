"""
Reports Router
--------------
Endpoints for reports summary and exports.
"""

from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import RequireManager, get_db
from src.core.logging import get_logger
from src.modules.reports.repository import reports_repository
from src.modules.reports.schemas import (
    ReportExportCreateRequest,
    ReportExportCreateResponse,
    ReportExportListResponse,
    ReportExportStatusResponse,
    ReportSummaryResponse,
    ReportTypesResponse,
    ReportXeroExportRequest,
)
from src.modules.reports.service import reports_service

logger = get_logger(__name__)

router = APIRouter(
    prefix="/reports",
    tags=["Reports"],
    dependencies=[RequireManager],
)


def _status_value(status: str | Enum) -> str:
    if isinstance(status, Enum):
        return status.value
    return str(status)


def _request_token(req: Request) -> str | None:
    auth_header = req.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip() or None
    return req.query_params.get("token")


def _append_token(url: str, token: str | None) -> str:
    if not token:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query["token"] = token
    return urlunparse(parsed._replace(query=urlencode(query)))


@router.get(
    "/summary",
    response_model=ReportSummaryResponse,
    summary="Report summary",
)
async def report_summary(
    db: AsyncSession = Depends(get_db),
    start_date: str = Query(...),
    end_date: str = Query(...),
    timezone: str | None = Query(None),
) -> ReportSummaryResponse:
    summary = await reports_service.get_summary(
        db,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )
    return ReportSummaryResponse(**summary)


@router.get(
    "/types",
    response_model=ReportTypesResponse,
    summary="Report types",
)
async def report_types(
    db: AsyncSession = Depends(get_db),
) -> ReportTypesResponse:
    items = await reports_service.get_report_types(db)
    return ReportTypesResponse(items=items)


@router.post(
    "/export",
    response_model=ReportExportCreateResponse,
    summary="Create report export",
)
async def create_export(
    request: ReportExportCreateRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportExportCreateResponse:
    result = await reports_service.create_export(
        db,
        report_id=request.report_id,
        format=request.format,
        start_date=request.start_date,
        end_date=request.end_date,
        timezone=request.timezone,
    )
    export = result["export"]
    status_value = _status_value(export.status)
    token = _request_token(req)
    download_url = (
        _append_token(
            f"{str(req.base_url).rstrip('/')}/api/v1/reports/exports/{export.id}/download",
            token,
        )
        if status_value == "ready"
        else None
    )
    return ReportExportCreateResponse(
        id=str(export.id),
        status=status_value,
        download_url=download_url,
    )


@router.get(
    "/exports",
    response_model=ReportExportListResponse,
    summary="List report exports",
)
async def list_exports(
    req: Request,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(6, ge=1, le=100),
    offset: int = Query(0, ge=0),
    report_id: str | None = Query(None),
    status: str | None = Query(None, pattern="^(ready|processing|failed)$"),
) -> ReportExportListResponse:
    exports, total = await reports_repository.list_exports(
        db,
        report_id=report_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    items = []
    base_url = str(req.base_url).rstrip("/")
    token = _request_token(req)
    for export in exports:
        status_value = _status_value(export.status)
        download_url = (
            _append_token(
                f"{base_url}/api/v1/reports/exports/{export.id}/download",
                token,
            )
            if status_value == "ready"
            else None
        )
        name = f"{export.report_id.title()} Report - {export.created_at.date().isoformat()}.{export.format.lower()}"
        items.append(
            {
                "id": str(export.id),
                "name": name,
                "report_id": export.report_id,
                "format": export.format,
                "status": status_value,
                "created_at": export.created_at,
                "size_kb": export.size_kb,
                "download_url": download_url,
            }
        )
    return ReportExportListResponse(items=items, total=total)


@router.get(
    "/exports/{export_id}",
    response_model=ReportExportStatusResponse,
    summary="Export status",
)
async def export_status(
    export_id: str,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportExportStatusResponse:
    export = await reports_repository.get_export(db, export_id)
    if not export:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    status_value = _status_value(export.status)
    token = _request_token(req)
    download_url = (
        _append_token(
            f"{str(req.base_url).rstrip('/')}/api/v1/reports/exports/{export.id}/download",
            token,
        )
        if status_value == "ready"
        else None
    )
    return ReportExportStatusResponse(
        id=str(export.id),
        status=status_value,
        download_url=download_url,
    )


@router.get(
    "/exports/{export_id}/download",
    summary="Download export",
)
async def download_export(
    export_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    export = await reports_repository.get_export(db, export_id)
    if not export or not export.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    if _status_value(export.status) != "ready":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Export not ready")
    file_path = Path(export.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=file_path.name,
    )


@router.post(
    "/export/xero",
    response_model=ReportExportCreateResponse,
    summary="Xero export",
)
async def export_xero(
    request: ReportXeroExportRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
) -> ReportExportCreateResponse:
    export_request = ReportExportCreateRequest(
        report_id="sales",
        format="CSV",
        start_date=request.start_date,
        end_date=request.end_date,
        timezone=request.timezone,
    )
    return await create_export(export_request, req, db)
