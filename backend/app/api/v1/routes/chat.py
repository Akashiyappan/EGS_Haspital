from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession, user_rate_limit
from app.core.config import settings
from app.core.pagination import Pagination
from app.integrations.storage import ImageStorage, get_storage, read_validated_image
from app.schemas.chat import (
    ClientId,
    ConversationCreate,
    ConversationRead,
    MarkReadRequest,
    MessageCreate,
    MessagePage,
    MessageRead,
    UnreadCount,
)
from app.schemas.common import Page, error_responses
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get(
    "/conversations",
    response_model=Page[ConversationRead],
    summary="My conversations with unread counts",
    responses=error_responses(401, 403),
)
async def list_conversations(
    user: CurrentUser, db: DbSession, page: Pagination
) -> Page[ConversationRead]:
    items, total = await chat_service.list_conversations(db, user, page)
    return Page[ConversationRead].build(items, total, page.page, page.page_size)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    summary="Open (or get) the conversation with a doctor/patient",
    description=(
        "Patients pass doctor_id, doctors pass patient_id. Requires an existing "
        "appointment between the two (care relationship)."
    ),
    responses=error_responses(400, 401, 403, 404, 422),
)
async def open_conversation(
    body: ConversationCreate, user: CurrentUser, db: DbSession
) -> ConversationRead:
    conversation = await chat_service.open_conversation(db, user, body)
    return ConversationRead(
        id=conversation.id,
        counterpart=chat_service.counterpart(conversation, user),
        last_message=None,
        last_message_at=conversation.last_message_at,
        unread_count=0,
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=MessagePage,
    summary="Message history (cursor paginated)",
    description=(
        "Default: the latest page. `before_id` loads older messages; `after_id` returns "
        "messages newer than the given id (use after reconnecting to catch up). "
        "Messages are always returned oldest first."
    ),
    responses=error_responses(401, 404),
)
async def list_messages(
    conversation_id: int,
    user: CurrentUser,
    db: DbSession,
    before_id: int | None = None,
    after_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> MessagePage:
    conversation = await chat_service.get_for_user(db, conversation_id, user)
    messages, has_more = await chat_service.list_messages(
        db, conversation, before_id=before_id, after_id=after_id, limit=limit
    )
    return MessagePage(items=[chat_service.to_message_read(m) for m in messages], has_more=has_more)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send a text message",
    description="Idempotent per `client_id`: retrying with the same id returns the original.",
    responses=error_responses(401, 404, 422),
)
async def send_message(
    conversation_id: int, body: MessageCreate, user: CurrentUser, db: DbSession
) -> MessageRead:
    conversation = await chat_service.get_for_user(db, conversation_id, user)
    message = await chat_service.send_message(
        db, conversation, user, body=body.body, client_id=body.client_id
    )
    return chat_service.to_message_read(message)


@router.post(
    "/conversations/{conversation_id}/images",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Send an image",
    description=(
        "Multipart upload, validated by content (JPEG/PNG/WebP, size-limited) and stored in "
        "Cloudinary as an authenticated asset; only a signed URL is stored and returned."
    ),
    responses=error_responses(400, 401, 404, 413, 422, 429, 503),
    dependencies=[Depends(user_rate_limit("upload", settings.RATE_LIMIT_UPLOAD))],
)
async def send_image(
    conversation_id: int,
    user: CurrentUser,
    db: DbSession,
    storage: Annotated[ImageStorage, Depends(get_storage)],
    file: Annotated[UploadFile, File(description="Image file")],
    caption: Annotated[str | None, Form(max_length=1000)] = None,
    client_id: Annotated[ClientId, Form()] = None,
) -> MessageRead:
    conversation = await chat_service.get_for_user(db, conversation_id, user)
    data, content_type = await read_validated_image(file)
    message = await chat_service.send_image(
        db,
        conversation,
        user,
        storage,
        data=data,
        content_type=content_type,
        caption=(caption or "").strip() or None,
        client_id=client_id,
    )
    return chat_service.to_message_read(message)


@router.post(
    "/conversations/{conversation_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark messages up to message_id as read",
    responses=error_responses(401, 404, 422),
)
async def mark_read(
    conversation_id: int, body: MarkReadRequest, user: CurrentUser, db: DbSession
) -> None:
    conversation = await chat_service.get_for_user(db, conversation_id, user)
    await chat_service.mark_read(db, conversation, user, body.message_id)


@router.get(
    "/unread-count",
    response_model=UnreadCount,
    summary="Total unread messages",
    responses=error_responses(401),
)
async def unread_count(user: CurrentUser, db: DbSession) -> UnreadCount:
    return UnreadCount(unread=await chat_service.total_unread(db, user))
