from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.models.enums import AIMessageRole
from app.models.notification import JSONType


class AIConversation(TimestampMixin, Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))

    __table_args__ = (Index("ix_ai_conversations_patient_id", "patient_id", "updated_at"),)


class AIMessage(TimestampMixin, Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE")
    )
    role: Mapped[AIMessageRole] = mapped_column(
        Enum(AIMessageRole, native_enum=False, length=16, create_constraint=True, name="ai_role")
    )
    content: Mapped[str] = mapped_column(Text)
    # Structured assistant output (urgency, specializations, doctor ids, tools used).
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict)

    __table_args__ = (Index("ix_ai_messages_conversation_id_id", "conversation_id", "id"),)
