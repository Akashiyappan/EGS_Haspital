"""AI assistant use cases: conversations, message exchange, and serialization.

Patient text is never written to application logs; only ids, lengths, tool
names, urgency and timings are logged.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import safety
from app.ai.agent import SymptomAgent
from app.ai.llm import LLMClient
from app.ai.prompts.symptom_assistant import PROMPT_VERSION, system_prompt
from app.ai.schemas import (
    AIConversationRead,
    AIMessageRead,
    AIResultRead,
    AppointmentConfirmation,
    AppointmentOption,
    AssistantResult,
)
from app.ai.tools import ToolContext, ToolRegistry, default_tools
from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.core.pagination import PageParams
from app.core.timeutils import clinic_today, utcnow
from app.models import AIConversation, AIMessage, AIMessageRole, Doctor, Patient, User
from app.services import doctor_service, slot_service, specialization_service

logger = logging.getLogger(__name__)


def build_registry() -> ToolRegistry:
    return ToolRegistry(default_tools())


_APPOINTMENT_INTENT = re.compile(r"\b(book|booking|appointment|schedule|available slot)\b", re.I)
_DOCTOR_LIST_INTENT = re.compile(r"\b(list|show|find|all)\b.{0,30}\bdoctors?\b", re.I)
_SPECIFIC_SLOT_SELECTION = re.compile(
    r"\b(it|that slot|that time|this slot|this time)\b|"
    r"\b(?:at\s*)?(?:(\d{1,2}):(\d{2})|(?:(\d{1,2})\s*(am|pm)))\b",
    re.I,
)


async def _retrieve_for_patient(
    db: AsyncSession, patient_text: str, now: datetime, ctx: ToolContext
) -> AssistantResult | None:
    """Deterministic database retrieval for directory and booking requests."""
    if _DOCTOR_LIST_INTENT.search(patient_text):
        doctors, _ = await doctor_service.list_doctors(
            db, PageParams(page=1, page_size=20), public=True
        )
        ctx.doctor_directory_ids = [doctor.id for doctor in doctors]
        ctx.seen_doctor_ids.update(ctx.doctor_directory_ids)
        return AssistantResult(
            summary=(
                f"Here are {len(doctors)} doctors currently listed at this hospital. "
                "Choose a doctor to view available appointment times."
                if doctors
                else "There are no active doctors listed right now. Please contact the hospital for help."
            ),
            response_type="follow_up",
        )

    if not _APPOINTMENT_INTENT.search(patient_text):
        return None

    specializations = await specialization_service.list_specializations(db, active_only=True)
    general = next((s for s in specializations if s.name.lower() == "general medicine"), None)
    target_specialization = general or (specializations[0] if specializations else None)
    doctors, _ = await doctor_service.list_doctors(
        db,
        PageParams(page=1, page_size=5),
        public=True,
        specialization_id=target_specialization.id if target_specialization else None,
    )
    ctx.seen_doctor_ids.update(doctor.id for doctor in doctors)
    first_day = clinic_today(now)
    for doctor in doctors:
        days = await slot_service.slots_for_range(
            db, doctor.id, first_day, first_day + timedelta(days=13), now
        )
        specialization = next(
            (s.name for s in doctor.specializations if target_specialization and s.id == target_specialization.id),
            doctor.specializations[0].name if doctor.specializations else "General Medicine",
        )
        for date, slots in days.items():
            for slot in slots:
                if not slot.available:
                    continue
                ctx.available_slots.add(
                    (doctor.id, slot.starts_at.astimezone(timezone.utc).isoformat())
                )
                ctx.appointment_options.append(
                    {
                        "doctor_id": doctor.id,
                        "doctor_name": f"Dr. {doctor.user.full_name}",
                        "specialization": specialization,
                        "starts_at": slot.starts_at.isoformat(),
                        "local_time": slot.starts_at.astimezone(settings.clinic_tz).strftime(
                            "%d %b %Y, %H:%M"
                        ),
                    }
                )
    ctx.appointment_options.sort(key=lambda option: option["starts_at"])
    ctx.appointment_options = ctx.appointment_options[:10]
    if not doctors:
        summary = f"I couldn't find an active {target_specialization.name if target_specialization else 'doctor'}. You can browse the doctor directory or contact the hospital."
    elif not ctx.appointment_options:
        summary = f"I found {target_specialization.name if target_specialization else 'doctors'}, but there are no open slots in the next two weeks. Please choose another specialty or contact the hospital."
    else:
        summary = f"I found appointment times with {target_specialization.name if target_specialization else 'doctors'}. Choose a slot below to book it."
    return AssistantResult(
        summary=summary,
        response_type="appointment",
        urgency="routine",
        recommended_specializations=[target_specialization.name] if target_specialization else [],
        recommended_doctor_ids=[doctor.id for doctor in doctors[:5]],
        appointment_options=[
            AppointmentOption.model_validate(option) for option in ctx.appointment_options
        ],
    )


# --- Conversations ---------------------------------------------------------------


def to_conversation_read(conversation: AIConversation) -> AIConversationRead:
    return AIConversationRead(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


async def list_conversations(
    db: AsyncSession, patient: Patient, page: PageParams
) -> tuple[list[AIConversation], int]:
    query = select(AIConversation).where(AIConversation.patient_id == patient.id)
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(AIConversation.updated_at.desc(), AIConversation.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    return list(rows), total


async def create_conversation(
    db: AsyncSession, patient: Patient, title: str | None
) -> AIConversation:
    conversation = AIConversation(patient_id=patient.id, title=title or "New consultation")
    db.add(conversation)
    await db.commit()
    return conversation


async def get_conversation(
    db: AsyncSession, patient: Patient, conversation_id: int
) -> AIConversation:
    conversation = await db.get(AIConversation, conversation_id)
    if conversation is None or conversation.patient_id != patient.id:
        raise NotFoundError("Conversation not found")
    return conversation


async def delete_conversation(db: AsyncSession, conversation: AIConversation) -> None:
    await db.delete(conversation)
    await db.commit()


async def list_messages(db: AsyncSession, conversation: AIConversation) -> list[AIMessage]:
    return list(
        await db.scalars(
            select(AIMessage)
            .where(AIMessage.conversation_id == conversation.id)
            .order_by(AIMessage.id)
        )
    )


async def to_message_reads(db: AsyncSession, messages: list[AIMessage]) -> list[AIMessageRead]:
    """Serialize messages, hydrating recommended doctors from the database
    (so a doctor who has since been deactivated is no longer shown)."""
    doctor_ids = {
        doctor_id
        for message in messages
        for doctor_id in (message.details or {}).get("result", {}).get("recommended_doctor_ids", [])
    }
    doctor_ids.update(
        doctor_id
        for message in messages
        for doctor_id in (message.details or {}).get("doctor_directory_ids", [])
    )
    doctors = await doctor_service.get_public_by_ids(db, doctor_ids)
    return [_to_message_read(message, doctors) for message in messages]


def _to_message_read(message: AIMessage, doctors: dict[int, Doctor]) -> AIMessageRead:
    result: AIResultRead | None = None
    raw = (message.details or {}).get("result")
    if message.role == AIMessageRole.ASSISTANT and raw:
        base = AssistantResult.model_validate(raw)
        result = AIResultRead(
            **base.model_dump(),
            recommended_doctors=[
                doctor_service.to_public(doctors[i])
                for i in base.recommended_doctor_ids
                if i in doctors
            ],
            doctor_directory=[
                doctor_service.to_public(doctors[i])
                for i in (message.details or {}).get("doctor_directory_ids", [])
                if i in doctors
            ],
            tools_used=(message.details or {}).get("tools_used", []),
        )
    return AIMessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        result=result,
        created_at=message.created_at,
    )


# --- Exchange --------------------------------------------------------------------


def _history_messages(history: list[AIMessage]) -> list[dict[str, Any]]:
    recent = history[-settings.AI_HISTORY_MESSAGES :]
    messages: list[dict[str, Any]] = []
    for message in recent:
        role = "user" if message.role == AIMessageRole.USER else "assistant"
        content = message.content
        if role == "assistant":
            result = (message.details or {}).get("result") or {}
            context = {
                key: result[key]
                for key in (
                    "urgency",
                    "possible_concerns",
                    "recommended_specializations",
                    "recommended_doctor_ids",
                    "next_steps",
                    "appointment_confirmation",
                )
                if result.get(key)
            }
            if context:
                content += "\n[Previous guidance context; use only if relevant, do not repeat automatically: "
                content += "; ".join(f"{key}={value}" for key, value in context.items()) + "]"
        messages.append({"role": role, "content": content})
    return messages


async def exchange(
    db: AsyncSession,
    conversation: AIConversation,
    patient: Patient,
    patient_user: User,
    text: str,
    llm: LLMClient | None,
) -> tuple[AIMessage, AIMessage]:
    """Run one user turn through the agent and persist both messages.

    `llm` is None when the provider isn't configured; emergency text still gets
    the deterministic emergency guidance in that case.
    """
    history = await list_messages(db, conversation)
    now = utcnow()
    ctx = ToolContext(
        db=db,
        now=now,
        patient=patient,
        patient_user=patient_user,
        current_text=text,
    )
    tools_used: list[str] = []
    termination = "not_run"

    if safety.is_prompt_injection(text):
        result = safety.refusal_result()
        termination = "refused"
    elif not safety.has_red_flags(text) and (
        _DOCTOR_LIST_INTENT.search(text)
        or (_APPOINTMENT_INTENT.search(text) and not _SPECIFIC_SLOT_SELECTION.search(text))
    ):
        result = await _retrieve_for_patient(db, text, now, ctx)
        if result is None:
            result = safety.fallback_result(text, "no matching hospital information")
        termination = "retrieval"
    elif llm is None:
        if safety.has_red_flags(text):
            result = safety.fallback_result(text, "assistant unavailable")
            termination = "unavailable"
        else:
            result = await _retrieve_for_patient(db, text, now, ctx)
            if result is None:
                raise ServiceUnavailableError(
                    "The AI assistant is not configured on this server", code="ai_unavailable"
                )
            termination = "retrieval_fallback"
    else:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": system_prompt(settings.CLINIC_TIMEZONE, clinic_today(now).isoformat()),
            },
            *_history_messages(history),
            {"role": "user", "content": text},
        ]
        run = await SymptomAgent(llm, build_registry()).run(messages, ctx)
        tools_used = [t.name for t in run.tool_traces if t.ok]
        termination = run.termination
        if run.result is None:
            result = None if safety.has_red_flags(text) else await _retrieve_for_patient(
                db, text, now, ctx
            )
            if result is None:
                reason = (
                    "the assistant is temporarily unavailable"
                    if run.termination in ("model_error", "timeout")
                    else "a valid answer could not be generated"
                )
                result = safety.fallback_result(text, reason)
        else:
            result = run.result

    specializations = await specialization_service.list_specializations(db, active_only=True)
    result = safety.enforce(
        result,
        patient_text=text,
        allowed_doctor_ids=ctx.seen_doctor_ids,
        known_specializations={s.name.lower(): s.name for s in specializations},
    )
    result = result.model_copy(
        update={
            "response_type": (
                "appointment" if ctx.appointment_options else result.response_type
            ),
            "appointment_options": [
                AppointmentOption.model_validate(option)
                for option in ctx.appointment_options[:10]
            ],
            "appointment_confirmation": (
                AppointmentConfirmation.model_validate(ctx.booked_appointment)
                if ctx.booked_appointment
                else None
            )
        }
    )

    user_message = AIMessage(
        conversation_id=conversation.id, role=AIMessageRole.USER, content=text, details={}
    )
    assistant_message = AIMessage(
        conversation_id=conversation.id,
        role=AIMessageRole.ASSISTANT,
        content=result.summary,
        details={
            "result": result.model_dump(mode="json"),
            "doctor_directory_ids": ctx.doctor_directory_ids,
            "tools_used": tools_used,
            "termination": termination,
            "prompt_version": PROMPT_VERSION,
            "model": settings.GROQ_MODEL,
        },
    )
    db.add_all([user_message, assistant_message])
    if not history and conversation.title == "New consultation":
        conversation.title = text[:60] + ("…" if len(text) > 60 else "")
    conversation.updated_at = utcnow()
    await db.commit()
    logger.info(
        "AI exchange conversation=%s input_chars=%s urgency=%s termination=%s tools=%s",
        conversation.id,
        len(text),
        result.urgency,
        termination,
        tools_used,
    )
    return user_message, assistant_message
