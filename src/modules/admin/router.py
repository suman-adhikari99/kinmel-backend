"""
Admin API Router
----------------
REST endpoints for audit logs and administrative queries.

🔐 ACCESS CONTROL:
All endpoints require MANAGER or ADMIN role.

Endpoints:
- GET /admin/audit-log - Query audit trail with filters
- GET /admin/audit-log/export.csv - Export as CSV
- GET /admin/audit-log/stats - Aggregated statistics

Design Principles:
1. Read-only access (audit logs are immutable)
2. Privacy-conscious (no PII in responses)
3. Efficient pagination for large datasets
4. Export-friendly for reporting
"""

import csv
import io
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.deps import (
    CurrentUser,
    DbSession,
    RequireManager,
)
from src.core.logging import get_logger
from src.core.security import Role, has_role_or_higher
from src.modules.admin.repository import audit_repository
from src.modules.admin.schemas import (
    AuditActionType,
    AuditLogQueryParams,
    AuditLogResponse,
    AuditReasonType,
    AuditStatsResponse,
    CSVExportParams,
)

logger = get_logger(__name__)


router = APIRouter(
    prefix="/admin",
    tags=["Admin & Audit"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions (requires MANAGER or higher)"},
    },
)


# ═══════════════════════════════════════════════════════════════════════════
# ROLE ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════════


def require_audit_access(user: CurrentUser) -> None:
    """
    Verify user has audit log access.
    
    Required: MANAGER or ADMIN role
    """
    if not has_role_or_higher(user.role, Role.MANAGER):
        logger.warning(
            "Audit access denied - insufficient role",
            user_id=user.sub,
            user_role=user.role,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": "Access to audit logs requires Manager or Admin role.",
                "code": "INSUFFICIENT_ROLE",
                "required_role": "MANAGER",
                "your_role": user.role.value,
            },
        )


# ═══════════════════════════════════════════════════════════════════════════
# AUDIT LOG ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/audit-log",
    response_model=AuditLogResponse,
    summary="Query audit log",
    description="""
    Query the immutable stock movement audit trail.
    
    **Access:** Manager and Admin roles only
    
    **Features:**
    - Filter by SKU, location, action type, date range, user
    - Pagination with limit/offset
    - Results ordered by timestamp (newest first)
    
    **Privacy:**
    - Internal IDs are not exposed
    - User emails are not shown (only names)
    
    **Example queries:**
    - All sales: `?action_type=sale`
    - SKU history: `?sku=MILK-2L-WHOLE`
    - Date range: `?start_date=2024-01-01&end_date=2024-01-31`
    - Combined: `?sku=MILK-2L&action_type=adjustment&start_date=2024-01-01`
    """,
    responses={
        200: {
            "description": "Audit log entries",
            "content": {
                "application/json": {
                    "example": {
                        "entries": [
                            {
                                "sku": "MILK-2L-WHOLE",
                                "product_name": "Whole Milk 2L",
                                "location_code": "FLOOR-A1",
                                "location_name": "Aisle 1 Floor Shelves",
                                "action_type": "sale",
                                "reason": "customer_sale",
                                "quantity_delta": -2,
                                "quantity_before": 50,
                                "quantity_after": 48,
                                "performed_by": "John Smith",
                                "timestamp": "2024-01-15T14:30:00Z",
                                "reference_id": "ORD-2024-001",
                                "reference_type": "order",
                                "notes": None,
                                "change_direction": "decrease",
                            }
                        ],
                        "total": 150,
                        "limit": 50,
                        "offset": 0,
                        "filters_applied": {"action_type": "sale"},
                        "has_more": True,
                        "page": 1,
                        "total_pages": 3,
                    }
                }
            },
        },
    },
)
async def get_audit_log(
    user: CurrentUser,
    db: DbSession,
    # ─────────────────────────────────────────────────────────────
    # Entity filters
    # ─────────────────────────────────────────────────────────────
    sku: Annotated[
        str | None,
        Query(
            description="Filter by product SKU (case-insensitive)",
            max_length=50,
            examples=["MILK-2L-WHOLE"],
        ),
    ] = None,
    location_code: Annotated[
        str | None,
        Query(
            description="Filter by location code",
            max_length=50,
            examples=["FLOOR-A1", "COLD-01"],
        ),
    ] = None,
    # ─────────────────────────────────────────────────────────────
    # Action filters
    # ─────────────────────────────────────────────────────────────
    action_type: Annotated[
        AuditActionType | None,
        Query(
            description="Filter by action type",
        ),
    ] = None,
    reason: Annotated[
        AuditReasonType | None,
        Query(
            description="Filter by reason code",
        ),
    ] = None,
    # ─────────────────────────────────────────────────────────────
    # User filter
    # ─────────────────────────────────────────────────────────────
    performed_by: Annotated[
        str | None,
        Query(
            description="Filter by user name (partial match)",
            max_length=100,
        ),
    ] = None,
    # ─────────────────────────────────────────────────────────────
    # Date filters
    # ─────────────────────────────────────────────────────────────
    start_date: Annotated[
        datetime | None,
        Query(
            description="Filter from date (ISO 8601)",
            examples=["2024-01-01T00:00:00Z"],
        ),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(
            description="Filter until date (ISO 8601)",
            examples=["2024-01-31T23:59:59Z"],
        ),
    ] = None,
    # ─────────────────────────────────────────────────────────────
    # Reference filter
    # ─────────────────────────────────────────────────────────────
    reference_id: Annotated[
        str | None,
        Query(
            description="Filter by reference ID (order, PO, etc.)",
            max_length=50,
        ),
    ] = None,
    # ─────────────────────────────────────────────────────────────
    # Pagination
    # ─────────────────────────────────────────────────────────────
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=500,
            description="Max records to return",
        ),
    ] = 50,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Records to skip",
        ),
    ] = 0,
) -> AuditLogResponse:
    """
    Query audit log with filters and pagination.
    
    🔐 MANAGER/ADMIN ONLY
    """
    # Enforce role
    require_audit_access(user)
    
    # Validate date range
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "start_date must be before end_date",
                "code": "INVALID_DATE_RANGE",
            },
        )
    
    # Build query params
    params = AuditLogQueryParams(
        sku=sku.upper() if sku else None,
        location_code=location_code.upper() if location_code else None,
        action_type=action_type,
        reason=reason,
        performed_by=performed_by,
        start_date=start_date,
        end_date=end_date,
        reference_id=reference_id,
        limit=limit,
        offset=offset,
    )
    
    # Execute query
    entries, total, filters_applied = await audit_repository.get_audit_logs(
        db, params
    )
    
    logger.info(
        "Audit log queried",
        user_id=user.sub,
        total_results=total,
        returned=len(entries),
        filters=filters_applied,
    )
    
    return AuditLogResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
        filters_applied=filters_applied,
    )


# ═══════════════════════════════════════════════════════════════════════════
# CSV EXPORT ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/audit-log/export.csv",
    summary="Export audit log as CSV",
    description="""
    Export audit log entries as a downloadable CSV file.
    
    **Access:** Manager and Admin roles only
    
    **Features:**
    - Same filters as `/audit-log` endpoint
    - Higher default limit (10,000 records)
    - Streams response for large exports
    
    **CSV columns:**
    timestamp, sku, product_name, location_code, location_name,
    action_type, reason, quantity_delta, quantity_before, quantity_after,
    performed_by, reference_id, reference_type, notes
    """,
    responses={
        200: {
            "description": "CSV file download",
            "content": {
                "text/csv": {
                    "example": "timestamp,sku,product_name,...\\n2024-01-15T14:30:00Z,MILK-2L,..."
                }
            },
        },
    },
)
async def export_audit_log_csv(
    user: CurrentUser,
    db: DbSession,
    # Same filters as audit-log endpoint
    sku: Annotated[str | None, Query(max_length=50)] = None,
    location_code: Annotated[str | None, Query(max_length=50)] = None,
    action_type: Annotated[AuditActionType | None, Query()] = None,
    reason: Annotated[AuditReasonType | None, Query()] = None,
    performed_by: Annotated[str | None, Query(max_length=100)] = None,
    start_date: Annotated[datetime | None, Query()] = None,
    end_date: Annotated[datetime | None, Query()] = None,
    reference_id: Annotated[str | None, Query(max_length=50)] = None,
    limit: Annotated[int, Query(ge=1, le=100000)] = 10000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> StreamingResponse:
    """
    Export audit log as CSV file.
    
    🔐 MANAGER/ADMIN ONLY
    """
    # Enforce role
    require_audit_access(user)
    
    # Build params
    params = AuditLogQueryParams(
        sku=sku.upper() if sku else None,
        location_code=location_code.upper() if location_code else None,
        action_type=action_type,
        reason=reason,
        performed_by=performed_by,
        start_date=start_date,
        end_date=end_date,
        reference_id=reference_id,
        limit=limit,
        offset=offset,
    )
    
    # Get data for CSV
    rows = await audit_repository.export_audit_logs_csv(db, params)
    
    logger.info(
        "Audit log CSV export",
        user_id=user.sub,
        rows_exported=len(rows),
    )
    
    # Generate CSV
    output = io.StringIO()
    
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    else:
        # Write header only for empty result
        fieldnames = [
            "timestamp", "sku", "product_name", "location_code", "location_name",
            "action_type", "reason", "quantity_delta", "quantity_before",
            "quantity_after", "performed_by", "reference_id", "reference_type", "notes",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
    
    # Reset to beginning
    output.seek(0)
    
    # Generate filename with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    filename = f"audit_log_export_{timestamp}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


# ═══════════════════════════════════════════════════════════════════════════
# STATISTICS ENDPOINT
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/audit-log/stats",
    response_model=AuditStatsResponse,
    summary="Get audit statistics",
    description="""
    Get aggregated statistics from the audit log.
    
    **Access:** Manager and Admin roles only
    
    **Statistics included:**
    - Total actions count
    - Total units increased/decreased
    - Breakdown by action type
    - Daily activity trends
    - Top products by movement count
    - Top users by action count
    
    **Default period:** Last 30 days
    """,
    responses={
        200: {
            "description": "Audit statistics",
            "content": {
                "application/json": {
                    "example": {
                        "period_start": "2024-01-01T00:00:00Z",
                        "period_end": "2024-01-31T23:59:59Z",
                        "total_actions": 1500,
                        "total_units_increased": 5000,
                        "total_units_decreased": 4500,
                        "net_stock_change": 500,
                        "by_action_type": [
                            {
                                "action_type": "sale",
                                "count": 1000,
                                "total_units_affected": 3500,
                                "average_units_per_action": 3.5,
                            }
                        ],
                        "by_day": [
                            {
                                "date": "2024-01-31",
                                "total_actions": 50,
                                "total_units_increased": 200,
                                "total_units_decreased": 150,
                                "net_change": 50,
                            }
                        ],
                        "top_products": [
                            {"sku": "MILK-2L", "name": "Whole Milk 2L", "movement_count": 150}
                        ],
                        "top_users": [
                            {"name": "John Smith", "action_count": 200}
                        ],
                    }
                }
            },
        },
    },
)
async def get_audit_stats(
    user: CurrentUser,
    db: DbSession,
    start_date: Annotated[
        datetime | None,
        Query(
            description="Period start (default: 30 days ago)",
            examples=["2024-01-01T00:00:00Z"],
        ),
    ] = None,
    end_date: Annotated[
        datetime | None,
        Query(
            description="Period end (default: now)",
            examples=["2024-01-31T23:59:59Z"],
        ),
    ] = None,
) -> AuditStatsResponse:
    """
    Get aggregated audit statistics.
    
    🔐 MANAGER/ADMIN ONLY
    """
    # Enforce role
    require_audit_access(user)
    
    # Validate date range
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "start_date must be before end_date",
                "code": "INVALID_DATE_RANGE",
            },
        )
    
    # Get stats
    stats = await audit_repository.get_audit_stats(
        db,
        start_date=start_date,
        end_date=end_date,
    )
    
    logger.info(
        "Audit stats queried",
        user_id=user.sub,
        period_start=stats["period_start"].isoformat(),
        period_end=stats["period_end"].isoformat(),
        total_actions=stats["total_actions"],
    )
    
    return AuditStatsResponse(**stats)


# ═══════════════════════════════════════════════════════════════════════════
# ACTION TYPES REFERENCE
# ═══════════════════════════════════════════════════════════════════════════


@router.get(
    "/audit-log/action-types",
    summary="List valid action types",
    description="Get list of valid action types for filtering.",
    response_model=dict[str, list[str]],
)
async def list_action_types(
    user: CurrentUser,
) -> dict[str, list[str]]:
    """
    Get list of valid action types and reasons.
    
    Useful for building filter UIs.
    """
    # No special role required - just authentication
    
    return {
        "action_types": [t.value for t in AuditActionType],
        "reasons": [r.value for r in AuditReasonType],
    }
