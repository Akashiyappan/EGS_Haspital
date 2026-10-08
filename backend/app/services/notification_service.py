"""Notification fan-out.

Business code describes *what* happened (`NotificationPayload`); this module
decides *how* it is delivered. Every notification is stored in-app (the source
of truth, de-duplicated per user by `dedupe_key`), then pushed over WebSocket
and, for selected types, by email. New channels (SMS, push) implement
`NotificationChannel` and are added to `CHANNELS`.

Usage inside a service:

    notifier = Notifier(db)
    await notifier.add(user_id, payload)   # staged in the current transaction
    await db.commit()
    await notifier.dispatch()              # external delivery only after commit
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.integrations.email import EmailMessage, get_email_sender
from app.models import Notification, NotificationType, User
from app.realtime.manager import manager

logger = logging.getLogger(__name__)

EMAIL_TYPES = frozenset(
    {
        NotificationType.APPOINTMENT_BOOKED,
        NotificationType.APPOINTMENT_CANCELLED,
        NotificationType.APPOINTMENT_REMINDER,
    }
)


@dataclass(frozen=True)
class NotificationPayload:
    type: NotificationType
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str | None = None


class NotificationChannel(Protocol):
    async def deliver(self, user: User, notification: Notification) -> None: ...


class RealtimeChannel:
    async def deliver(self, user: User, notification: Notification) -> None:
        await manager.send_to_user(user.id, "notification.created", serialize(notification))


class EmailChannel:
    async def deliver(self, user: User, notification: Notification) -> None:
        if notification.type not in EMAIL_TYPES:
            return
        await get_email_sender().send(
            EmailMessage(to=user.email, subject=notification.title, text=notification.body)
        )


CHANNELS: list[NotificationChannel] = [RealtimeChannel(), EmailChannel()]


def serialize(notification: Notification) -> dict[str, Any]:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "data": notification.data,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat(),
    }


class Notifier:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._staged: list[Notification] = []

    async def add(self, user_id: int, payload: NotificationPayload) -> None:
        notification = Notification(
            user_id=user_id,
            type=payload.type.value,
            title=payload.title,
            body=payload.body,
            data=payload.data,
            dedupe_key=payload.dedupe_key,
        )
        if payload.dedupe_key:
            # Savepoint so a duplicate only drops this notification, not the
            # surrounding business transaction.
            try:
                async with self.db.begin_nested():
                    self.db.add(notification)
            except IntegrityError:
                logger.info("Skipped duplicate notification %s", payload.dedupe_key)
                return
        else:
            self.db.add(notification)
        self._staged.append(notification)

    async def dispatch(self) -> None:
        staged, self._staged = self._staged, []
        for notification in staged:
            user = await self.db.get(User, notification.user_id)
            if user is None or not user.is_active:
                continue
            for channel in CHANNELS:
                try:
                    await channel.deliver(user, notification)
                except Exception:  # one failing channel must not block the others
                    logger.exception("Notification channel %s failed", type(channel).__name__)


async def list_for_user(
    db: AsyncSession, user_id: int, *, unread_only: bool, limit: int, offset: int
) -> tuple[list[Notification], int]:
    query = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(query.order_by(Notification.id.desc()).limit(limit).offset(offset))
    return list(rows), total


async def unread_count(db: AsyncSession, user_id: int) -> int:
    return (
        await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        or 0
    )


async def mark_read(db: AsyncSession, user_id: int, notification_id: int | None) -> int:
    """Mark one (or, with None, all) of the user's notifications read."""
    statement = (
        update(Notification)
        .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )
    if notification_id is not None:
        statement = statement.where(Notification.id == notification_id)
    result = await db.execute(statement)
    await db.commit()
    return int(result.rowcount or 0)  # type: ignore[attr-defined]


def format_clinic_time(value: datetime) -> str:
    from app.core.config import settings

    local = value.astimezone(settings.clinic_tz)
    return local.strftime("%a %d %b %Y, %I:%M %p ") + (local.tzname() or "")
