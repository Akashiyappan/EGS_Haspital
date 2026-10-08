"""Doctor-patient messaging. Messages are persisted first (the database is the
source of truth) and then pushed to connected participants over WebSocket."""

import logging
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import PageParams
from app.core.timeutils import utcnow
from app.integrations.storage import ImageStorage, StoredImage
from app.models import (
    Conversation,
    Doctor,
    Message,
    MessageAttachment,
    MessageType,
    NotificationType,
    Patient,
    Role,
    User,
)
from app.realtime.manager import manager
from app.schemas.chat import (
    AttachmentRead,
    ConversationCreate,
    ConversationRead,
    Counterpart,
    MessageRead,
)
from app.services import appointment_service
from app.services.notification_service import NotificationPayload, Notifier

logger = logging.getLogger(__name__)

MAX_PAGE = 100


def _with_parties(query: Select[tuple[Conversation]]) -> Select[tuple[Conversation]]:
    return query.options(selectinload(Conversation.doctor), selectinload(Conversation.patient))


def is_participant(conversation: Conversation, user: User) -> bool:
    return user.id in (conversation.doctor.user_id, conversation.patient.user_id)


def other_user_id(conversation: Conversation, user: User) -> int:
    doctor_uid, patient_uid = conversation.doctor.user_id, conversation.patient.user_id
    return patient_uid if user.id == doctor_uid else doctor_uid


def counterpart(conversation: Conversation, user: User) -> Counterpart:
    if user.id == conversation.doctor.user_id:
        other = conversation.patient.user
        return Counterpart(
            user_id=other.id,
            doctor_id=None,
            patient_id=conversation.patient_id,
            full_name=other.full_name,
            avatar_url=other.avatar_url,
            role=Role.PATIENT.value,
            online=manager.is_online(other.id),
        )
    other = conversation.doctor.user
    return Counterpart(
        user_id=other.id,
        doctor_id=conversation.doctor_id,
        patient_id=None,
        full_name=other.full_name,
        avatar_url=other.avatar_url,
        role=Role.DOCTOR.value,
        online=manager.is_online(other.id),
    )


def to_message_read(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        conversation_id=message.conversation_id,
        sender_id=message.sender_id,
        message_type=message.message_type,
        body=message.body,
        client_id=message.client_id,
        attachments=[
            AttachmentRead(
                id=a.id,
                url=a.url,
                content_type=a.content_type,
                width=a.width,
                height=a.height,
                bytes=a.bytes,
            )
            for a in message.attachments
        ],
        created_at=message.created_at,
    )


async def get_for_user(db: AsyncSession, conversation_id: int, user: User) -> Conversation:
    conversation = await db.scalar(
        _with_parties(select(Conversation).where(Conversation.id == conversation_id))
    )
    # Non-participants (admins included) get a 404: conversations are private.
    if conversation is None or not is_participant(conversation, user):
        raise NotFoundError("Conversation not found")
    return conversation


async def open_conversation(db: AsyncSession, user: User, data: ConversationCreate) -> Conversation:
    if user.role == Role.PATIENT:
        if data.doctor_id is None:
            raise AppError("doctor_id is required", code="doctor_required")
        patient_id = await db.scalar(select(Patient.id).where(Patient.user_id == user.id))
        doctor_id = await db.scalar(
            select(Doctor.id)
            .join(User, Doctor.user_id == User.id)
            .where(Doctor.id == data.doctor_id, User.is_active.is_(True), User.deleted_at.is_(None))
        )
        if doctor_id is None:
            raise NotFoundError("Doctor not found")
    elif user.role == Role.DOCTOR:
        if data.patient_id is None:
            raise AppError("patient_id is required", code="patient_required")
        doctor_id = await db.scalar(select(Doctor.id).where(Doctor.user_id == user.id))
        patient_id = data.patient_id
    else:
        raise ForbiddenError("Only doctors and patients can use chat")

    if patient_id is None or doctor_id is None:
        raise ForbiddenError()
    # Minimum-necessary access: chat requires an existing care relationship.
    if not await appointment_service.doctor_has_patient(db, doctor_id, patient_id):
        raise ForbiddenError(
            "Messaging is available once an appointment has been booked",
            code="no_care_relationship",
        )

    lookup = _with_parties(
        select(Conversation).where(
            Conversation.doctor_id == doctor_id, Conversation.patient_id == patient_id
        )
    )
    existing = await db.scalar(lookup)
    if existing:
        return existing
    db.add(Conversation(doctor_id=doctor_id, patient_id=patient_id))
    try:
        await db.commit()
    except IntegrityError:  # created concurrently by the other participant
        await db.rollback()
    conversation = await db.scalar(lookup)
    if conversation is None:
        raise ConflictError("Could not open the conversation; please retry", code="conflict")
    return conversation


async def list_conversations(
    db: AsyncSession, user: User, page: PageParams
) -> tuple[list[ConversationRead], int]:
    if user.role == Role.PATIENT:
        owner = select(Patient.id).where(Patient.user_id == user.id).scalar_subquery()
        query = select(Conversation).where(Conversation.patient_id == owner)
        last_read = Conversation.patient_last_read_message_id
    elif user.role == Role.DOCTOR:
        owner = select(Doctor.id).where(Doctor.user_id == user.id).scalar_subquery()
        query = select(Conversation).where(Conversation.doctor_id == owner)
        last_read = Conversation.doctor_last_read_message_id
    else:
        raise ForbiddenError("Only doctors and patients can use chat")

    unread = (
        select(func.count(Message.id))
        .where(
            Message.conversation_id == Conversation.id,
            Message.sender_id != user.id,
            Message.id > func.coalesce(last_read, 0),
        )
        .correlate(Conversation)
        .scalar_subquery()
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (
        await db.execute(
            _with_parties(query.add_columns(unread))
            .order_by(
                func.coalesce(Conversation.last_message_at, Conversation.created_at).desc(),
                Conversation.id.desc(),
            )
            .limit(page.page_size)
            .offset(page.offset)
        )
    ).all()

    conversation_ids = [row[0].id for row in rows]
    last_messages: dict[int, Message] = {}
    if conversation_ids:
        latest_ids = (
            select(func.max(Message.id))
            .where(Message.conversation_id.in_(conversation_ids))
            .group_by(Message.conversation_id)
        )
        for message in await db.scalars(select(Message).where(Message.id.in_(latest_ids))):
            last_messages[message.conversation_id] = message

    items = [
        ConversationRead(
            id=conversation.id,
            counterpart=counterpart(conversation, user),
            last_message=(
                to_message_read(last_messages[conversation.id])
                if conversation.id in last_messages
                else None
            ),
            last_message_at=conversation.last_message_at,
            unread_count=int(count or 0),
        )
        for conversation, count in rows
    ]
    return items, total


async def list_messages(
    db: AsyncSession,
    conversation: Conversation,
    *,
    before_id: int | None,
    after_id: int | None,
    limit: int,
) -> tuple[list[Message], bool]:
    """Cursor pagination by message id (monotonic, so ordering is stable).

    - after_id: messages newer than a known id, oldest first (reconnect catch-up)
    - before_id / none: the page of older messages, returned oldest first
    """
    limit = max(1, min(limit, MAX_PAGE))
    query = select(Message).where(Message.conversation_id == conversation.id)
    if after_id is not None:
        rows = list(
            await db.scalars(
                query.where(Message.id > after_id).order_by(Message.id.asc()).limit(limit + 1)
            )
        )
        return rows[:limit], len(rows) > limit
    if before_id is not None:
        query = query.where(Message.id < before_id)
    rows = list(await db.scalars(query.order_by(Message.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    return list(reversed(rows[:limit])), has_more


async def _existing_by_client_id(
    db: AsyncSession, conversation_id: int, sender_id: int, client_id: str
) -> Message | None:
    message: Message | None = await db.scalar(
        select(Message).where(
            Message.conversation_id == conversation_id,
            Message.sender_id == sender_id,
            Message.client_id == client_id,
        )
    )
    return message


async def send_message(
    db: AsyncSession,
    conversation: Conversation,
    sender: User,
    *,
    body: str | None,
    client_id: str | None,
    image: StoredImage | None = None,
) -> Message:
    if client_id:  # idempotent retry: return the message that already exists
        existing = await _existing_by_client_id(db, conversation.id, sender.id, client_id)
        if existing:
            return existing

    message = Message(
        conversation_id=conversation.id,
        sender_id=sender.id,
        message_type=MessageType.IMAGE if image else MessageType.TEXT,
        body=body,
        client_id=client_id,
    )
    # Always initialise the collection: a lazy load on a new object would need IO.
    message.attachments = []
    if image:
        message.attachments = [
            MessageAttachment(
                public_id=image.public_id,
                url=image.url,
                delivery_type=image.delivery_type,
                content_type=image.content_type,
                format=image.format,
                bytes=image.bytes,
                width=image.width,
                height=image.height,
            )
        ]
    db.add(message)
    conversation.last_message_at = utcnow()

    recipient_id = other_user_id(conversation, sender)
    recipient_last_read = (
        conversation.patient_last_read_message_id
        if recipient_id == conversation.patient.user_id
        else conversation.doctor_last_read_message_id
    )
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        if client_id:
            existing = await _existing_by_client_id(db, conversation.id, sender.id, client_id)
            if existing:
                return existing
        raise

    # One notification per unread streak, not one per message.
    notifier = Notifier(db)
    await notifier.add(
        recipient_id,
        NotificationPayload(
            NotificationType.NEW_MESSAGE,
            "New message",
            f"You have a new message from {_display_name(sender)}.",
            {"conversation_id": conversation.id},
            dedupe_key=f"chat:{conversation.id}:after:{recipient_last_read or 0}",
        ),
    )
    await db.commit()

    payload = to_message_read(message).model_dump(mode="json")
    await manager.send_to_users([sender.id, recipient_id], "message.created", payload)
    await notifier.dispatch()
    return message


def _display_name(user: User) -> str:
    return f"Dr. {user.full_name}" if user.role == Role.DOCTOR else user.full_name


async def send_image(
    db: AsyncSession,
    conversation: Conversation,
    sender: User,
    storage: ImageStorage,
    *,
    data: bytes,
    content_type: str,
    caption: str | None,
    client_id: str | None,
) -> Message:
    if client_id:
        existing = await _existing_by_client_id(db, conversation.id, sender.id, client_id)
        if existing:
            return existing
    image = await storage.upload_image(
        data, folder=f"chat/{conversation.id}", content_type=content_type, private=True
    )
    try:
        return await send_message(
            db, conversation, sender, body=caption, client_id=client_id, image=image
        )
    except Exception:
        await storage.delete(image.public_id, image.delivery_type)  # don't orphan the asset
        raise


async def mark_read(
    db: AsyncSession, conversation: Conversation, user: User, message_id: int
) -> int | None:
    latest = await db.scalar(
        select(func.max(Message.id)).where(
            Message.conversation_id == conversation.id, Message.id <= message_id
        )
    )
    if latest is None:
        return None
    is_doctor = user.id == conversation.doctor.user_id
    current = (
        conversation.doctor_last_read_message_id
        if is_doctor
        else conversation.patient_last_read_message_id
    )
    if current is not None and current >= latest:
        return current
    if is_doctor:
        conversation.doctor_last_read_message_id = latest
    else:
        conversation.patient_last_read_message_id = latest
    await db.commit()
    await manager.send_to_user(
        other_user_id(conversation, user),
        "conversation.read",
        {"conversation_id": conversation.id, "reader_id": user.id, "message_id": latest},
    )
    return latest


async def total_unread(db: AsyncSession, user: User) -> int:
    if user.role == Role.PATIENT:
        mine = (
            Conversation.patient_id
            == select(Patient.id).where(Patient.user_id == user.id).scalar_subquery()
        )
        last_read = Conversation.patient_last_read_message_id
    elif user.role == Role.DOCTOR:
        mine = (
            Conversation.doctor_id
            == select(Doctor.id).where(Doctor.user_id == user.id).scalar_subquery()
        )
        last_read = Conversation.doctor_last_read_message_id
    else:
        return 0
    return (
        await db.scalar(
            select(func.count(Message.id))
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(mine, Message.sender_id != user.id, Message.id > func.coalesce(last_read, 0))
        )
        or 0
    )


async def counterpart_user_ids(db: AsyncSession, user: User) -> list[int]:
    """Users who share a conversation with `user` (for presence updates)."""
    rows = await db.execute(
        select(Doctor.user_id, Patient.user_id)
        .select_from(Conversation)
        .join(Doctor, Conversation.doctor_id == Doctor.id)
        .join(Patient, Conversation.patient_id == Patient.id)
        .where(or_(Doctor.user_id == user.id, Patient.user_id == user.id))
    )
    return [d if p == user.id else p for d, p in rows]


def presence_payload(user: User, online: bool) -> dict[str, Any]:
    return {"user_id": user.id, "online": online}
