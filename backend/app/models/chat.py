from datetime import datetime

from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime
from app.models.doctor import Doctor
from app.models.enums import MessageType
from app.models.patient import Patient


class Conversation(TimestampMixin, Base):
    """One persistent thread per doctor-patient pair."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"))
    last_message_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    doctor_last_read_message_id: Mapped[int | None] = mapped_column(Integer)
    patient_last_read_message_id: Mapped[int | None] = mapped_column(Integer)

    doctor: Mapped[Doctor] = relationship(lazy="raise")
    patient: Mapped[Patient] = relationship(lazy="raise")

    __table_args__ = (
        UniqueConstraint("doctor_id", "patient_id", name="uq_conversations_doctor_patient"),
        Index("ix_conversations_patient_last", "patient_id", "last_message_at"),
        Index("ix_conversations_doctor_last", "doctor_id", "last_message_at"),
    )


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType, native_enum=False, length=16, create_constraint=True, name="message_type")
    )
    body: Mapped[str | None] = mapped_column(Text)
    # Client-generated idempotency key so a retried send never duplicates a message.
    client_id: Mapped[str | None] = mapped_column(String(64))

    attachments: Mapped[list["MessageAttachment"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_messages_conversation_id_id", "conversation_id", "id"),
        UniqueConstraint("conversation_id", "sender_id", "client_id", name="uq_messages_client_id"),
    )


class MessageAttachment(TimestampMixin, Base):
    """Image metadata only; the binary lives in Cloudinary."""

    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    public_id: Mapped[str] = mapped_column(String(255))
    # Signed delivery URL for `authenticated` assets; only returned to participants.
    url: Mapped[str] = mapped_column(String(1000))
    delivery_type: Mapped[str] = mapped_column(String(32))
    content_type: Mapped[str] = mapped_column(String(64))
    format: Mapped[str | None] = mapped_column(String(16))
    bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
