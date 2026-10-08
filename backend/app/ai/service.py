"""AI assistant use cases: conversations, message exchange, and serialization.

Patient text is never written to application logs; only ids, lengths, tool
names, urgency and timings are logged.
"""

import logging
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
    AssistantResult,
)
from app.ai.tools import ToolContext, ToolRegistry, default_tools
from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.core.pagination import PageParams
from app.core.timeutils import clinic_today, utcnow
from app.models import AIConversation, AIMessage, AIMessageRole, Doctor, Patient, User
from app.services import doctor_service, specialization_service

logger = logging.getLogger(__name__)


def build_registry() -> ToolRegistry:
    return ToolRegistry(default_tools())


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
    return [
        {
            "role": "user" if m.role == AIMessageRole.USER else "assistant",
            "content": m.content,
        }
        for m in recent
    ]


async def exchange(
    db: AsyncSession,
    conversation: AIConversation,
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
    ctx = ToolContext(db=db, now=now)
    tools_used: list[str] = []
    termination = "not_run"

    if safety.is_prompt_injection(text):
        result = safety.refusal_result()
        termination = "refused"
    elif llm is None:
        if not safety.has_red_flags(text):
            raise ServiceUnavailableError(
                "The AI assistant is not configured on this server", code="ai_unavailable"
            )
        result = safety.fallback_result(text, "assistant unavailable")
        termination = "unavailable"
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
            if run.termination in ("model_error", "timeout") and not safety.has_red_flags(text):
                raise ServiceUnavailableError(
                    "The AI assistant is temporarily unavailable. Please try again shortly.",
                    code="ai_unavailable",
                )
            result = safety.fallback_result(text, "no valid answer")
        else:
            result = run.result

    specializations = await specialization_service.list_specializations(db, active_only=True)
    result = safety.enforce(
        result,
        patient_text=text,
        allowed_doctor_ids=ctx.seen_doctor_ids,
        known_specializations={s.name.lower(): s.name for s in specializations},
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
