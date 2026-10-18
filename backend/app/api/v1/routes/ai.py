from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from app.ai import service as ai_service
from app.ai.llm import LLMClient, get_llm_client
from app.ai.schemas import (
    AIAppointmentBook,
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
from app.core.timeutils import ensure_utc, utcnow
from app.models import AIMessage, AIMessageRole
from app.schemas.common import Page, error_responses
from app.services import appointment_service

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
        db, conversation, patient, user, body.content, llm
    )
    user_read, assistant_read = await ai_service.to_message_reads(
        db, [user_message, assistant_message]
    )
    return AIExchangeRead(user_message=user_read, assistant_message=assistant_read)


@router.post(
    "/conversations/{conversation_id}/book",
    response_model=AIExchangeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book a selected appointment slot from the assistant chat",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def book_from_chat(
    conversation_id: int,
    body: AIAppointmentBook,
    request: Request,
    patient: CurrentPatient,
    user: PatientUser,
    db: DbSession,
) -> AIExchangeRead:
    conversation = await ai_service.get_conversation(db, patient, conversation_id)
    appointment = await appointment_service.book(
        db,
        patient,
        user,
        doctor_id=body.doctor_id,
        starts_at=body.starts_at,
        reason=None,
        request=request,
    )
    doctor_name = f"Dr. {appointment.doctor.user.full_name}"
    confirmation = {
        "id": appointment.id,
        "doctor_id": appointment.doctor_id,
        "doctor_name": doctor_name,
        "starts_at": appointment.starts_at.isoformat(),
        "status": appointment.status.value,
    }

    # Remove this slot from the saved offer so it cannot look bookable again.
    last_assistant = await db.scalar(
        select(AIMessage)
        .where(
            AIMessage.conversation_id == conversation.id,
            AIMessage.role == AIMessageRole.ASSISTANT,
        )
        .order_by(AIMessage.id.desc())
        .limit(1)
    )
    if last_assistant:
        details = dict(last_assistant.details or {})
        result = dict(details.get("result") or {})
        result["appointment_options"] = [
            option
            for option in result.get("appointment_options", [])
            if not (
                option.get("doctor_id") == body.doctor_id
                and ensure_utc(datetime.fromisoformat(option["starts_at"]))
                == ensure_utc(body.starts_at)
            )
        ]
        details["result"] = result
        last_assistant.details = details

    user_message = AIMessage(
        conversation_id=conversation.id,
        role=AIMessageRole.USER,
        content=f"Book an appointment with {doctor_name} at {appointment.starts_at.isoformat()}.",
        details={},
    )
    assistant_message = AIMessage(
        conversation_id=conversation.id,
        role=AIMessageRole.ASSISTANT,
        content=f"Your appointment with {doctor_name} is booked.",
        details={
            "result": {
                "summary": f"Your appointment with {doctor_name} is booked.",
                "response_type": "appointment",
                "urgency": "routine",
                "possible_concerns": [],
                "recommended_specializations": [],
                "recommended_doctor_ids": [],
                "next_steps": [],
                "follow_up_questions": [],
                "emergency_message": None,
                "disclaimer": "This assistant provides general health information only. It is not a medical diagnosis and does not replace advice from a qualified doctor.",
                "appointment_confirmation": confirmation,
                "appointment_options": [],
            }
        },
    )
    db.add_all([user_message, assistant_message])
    conversation.updated_at = utcnow()
    await db.commit()
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
