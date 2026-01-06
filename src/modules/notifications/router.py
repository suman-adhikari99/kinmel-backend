"""
Notifications Router
--------------------
Endpoints for staff notification center.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from src.api.deps import CurrentUser, DbSession
from src.modules.notifications.repository import RETENTION_DAYS, notifications_repository
from src.modules.notifications.schemas import (
    NotificationDeleteResponse,
    NotificationReadResponse,
    NotificationsListResponse,
    NotificationsReadAllResponse,
)
from src.modules.notifications.service import notifications_service, sse_stream


router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
    responses={401: {"description": "Not authenticated"}},
)


@router.get(
    "",
    response_model=NotificationsListResponse,
    summary="List notifications",
)
async def list_notifications(
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    filter_by: str = Query("all", alias="filter", pattern="^(all|unread)$"),
    notif_type: str | None = Query(None, alias="type", pattern="^(order|stock|alert|success)$"),
    since: datetime | None = Query(None),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
) -> NotificationsListResponse:
    items, total, unread_count = await notifications_repository.list_notifications(
        db,
        user_id=user.sub,
        limit=limit,
        offset=offset,
        filter_by=filter_by,
        notif_type=notif_type,
        since=since,
        sort_dir=sort_dir,
    )
    return NotificationsListResponse(
        items=items,
        total=total,
        unread_count=unread_count,
        retention_days=RETENTION_DAYS,
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationReadResponse,
    summary="Mark notification as read",
)
async def mark_read(
    notification_id: str,
    user: CurrentUser,
    db: DbSession,
) -> NotificationReadResponse:
    read_at = await notifications_repository.mark_read(
        db,
        notification_id=notification_id,
        user_id=user.sub,
    )
    if read_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    await db.commit()
    await notifications_service.publish_read(notification_id, read_at)
    return NotificationReadResponse(id=notification_id, read=True, read_at=read_at)


@router.post(
    "/read-all",
    response_model=NotificationsReadAllResponse,
    summary="Mark all notifications as read",
)
async def mark_all_read(
    user: CurrentUser,
    db: DbSession,
) -> NotificationsReadAllResponse:
    updated_count = await notifications_repository.mark_all_read(db, user_id=user.sub)
    await db.commit()
    return NotificationsReadAllResponse(success=True, updated_count=updated_count)


@router.delete(
    "/{notification_id}",
    response_model=NotificationDeleteResponse,
    summary="Delete notification",
)
async def delete_notification(
    notification_id: str,
    user: CurrentUser,
    db: DbSession,
) -> NotificationDeleteResponse:
    deleted = await notifications_repository.delete_notification(
        db,
        notification_id=notification_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    await db.commit()
    await notifications_service.publish_deleted(notification_id)
    return NotificationDeleteResponse(success=True)


@router.get(
    "/stream",
    summary="Notification stream",
)
async def notification_stream(
    user: CurrentUser,
) -> StreamingResponse:
    return StreamingResponse(sse_stream(), media_type="text/event-stream")
