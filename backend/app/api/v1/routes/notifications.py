from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.core.pagination import Pagination
from app.schemas.chat import UnreadCount
from app.schemas.common import Page, error_responses
from app.schemas.notification import NotificationRead
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get(
    "",
    response_model=Page[NotificationRead],
    summary="My notifications (newest first)",
    responses=error_responses(401),
)
async def list_notifications(
    user: CurrentUser, db: DbSession, page: Pagination, unread_only: bool = False
) -> Page[NotificationRead]:
    items, total = await notification_service.list_for_user(
        db, user.id, unread_only=unread_only, limit=page.page_size, offset=page.offset
    )
    return Page[NotificationRead].build(
        [NotificationRead.model_validate(n) for n in items], total, page.page, page.page_size
    )


@router.get(
    "/unread-count",
    response_model=UnreadCount,
    summary="Unread notification count",
    responses=error_responses(401),
)
async def unread_count(user: CurrentUser, db: DbSession) -> UnreadCount:
    return UnreadCount(unread=await notification_service.unread_count(db, user.id))


@router.post(
    "/{notification_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark one notification read",
    responses=error_responses(401),
)
async def mark_read(notification_id: int, user: CurrentUser, db: DbSession) -> None:
    await notification_service.mark_read(db, user.id, notification_id)


@router.post(
    "/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark all notifications read",
    responses=error_responses(401),
)
async def mark_all_read(user: CurrentUser, db: DbSession) -> None:
    await notification_service.mark_read(db, user.id, None)
