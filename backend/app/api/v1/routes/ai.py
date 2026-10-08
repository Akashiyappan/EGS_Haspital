from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.ai import service as ai_service
from app.ai.llm import LLMClient, get_llm_client
from app.ai.schemas import (
    AIConversationCreate,
    AIConversationRead,
    AIExchangeRead,
    AIMessageCreate,
    AIMessageRead,
)
from app.api.deps import CurrentPatient, DbSession, PatientUser, user_rate_limit
from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.pagination import Pagination
from app.schemas.common import Page, error_responses

router = APIRouter(prefix="/ai", tags=["ai assistant"])


def optional_llm_client() -> LLMClient | None:
    try:
        return get_llm_client()
    except ServiceUnavailableError:
        return None


@router.get(
    "/conversations",
    response_model=Page[AIConversationRead],
    summary="My assistant conversations",
    responses=error_responses(401, 403),
)
async def list_conversations(
    patient: CurrentPatient, db: DbSession, page: Pagination
) -> Page[AIConversationRead]:
    items, total = await ai_service.list_conversations(db, patient, page)
    return Page[AIConversationRead].build(
        [ai_service.to_conversation_read(c) for c in items], total, page.page, page.page_size
    )


@router.post(
    "/conversations",
    response_model=AIConversationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new assistant conversation",
    responses=error_responses(401, 403, 422),
)
async def create_conversation(
    body: AIConversationCreate, patient: CurrentPatient, db: DbSession
) -> AIConversationRead:
    conversation = await ai_service.create_conversation(db, patient, body.title)
    return ai_service.to_conversation_read(conversation)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[AIMessageRead],
    summary="Conversation messages",
    responses=error_responses(401, 403, 404),
)
async def list_messages(
    conversation_id: int, patient: CurrentPatient, db: DbSession
) -> list[AIMessageRead]:
    conversation = await ai_service.get_conversation(db, patient, conversation_id)
    return await ai_service.to_message_reads(db, await ai_service.list_messages(db, conversation))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AIExchangeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Describe symptoms and get guidance",
    description=(
        "Runs the symptom assistant. It may call backend tools to look up real "
        "specializations, doctors and availability. Output is informational, not a diagnosis; "
        "emergency symptoms always receive emergency-care guidance."
    ),
    responses=error_responses(401, 403, 404, 422, 429, 503),
    dependencies=[Depends(user_rate_limit("ai", settings.RATE_LIMIT_AI))],
)
async def send_message(
    conversation_id: int,
    body: AIMessageCreate,
    patient: CurrentPatient,
    user: PatientUser,
    db: DbSession,
    llm: Annotated[LLMClient | None, Depends(optional_llm_client)],
) -> AIExchangeRead:
    conversation = await ai_service.get_conversation(db, patient, conversation_id)
    user_message, assistant_message = await ai_service.exchange(
        db, conversation, user, body.content, llm
    )
    user_read, assistant_read = await ai_service.to_message_reads(
        db, [user_message, assistant_message]
    )
    return AIExchangeRead(user_message=user_read, assistant_message=assistant_read)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an assistant conversation",
    responses=error_responses(401, 403, 404),
)
async def delete_conversation(conversation_id: int, patient: CurrentPatient, db: DbSession) -> None:
    conversation = await ai_service.get_conversation(db, patient, conversation_id)
    await ai_service.delete_conversation(db, conversation)
