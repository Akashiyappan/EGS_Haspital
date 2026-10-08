from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints, model_validator

from app.models.enums import MessageType

ClientId = Annotated[
    str | None, StringConstraints(strip_whitespace=True, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
]


class ConversationCreate(BaseModel):
    """Patients pass doctor_id, doctors pass patient_id."""

    doctor_id: int | None = None
    patient_id: int | None = None

    @model_validator(mode="after")
    def _one(self) -> Self:
        if (self.doctor_id is None) == (self.patient_id is None):
            raise ValueError("Provide exactly one of doctor_id or patient_id")
        return self


class Counterpart(BaseModel):
    user_id: int
    doctor_id: int | None
    patient_id: int | None
    full_name: str
    avatar_url: str | None
    role: str
    online: bool


class AttachmentRead(BaseModel):
    id: int
    url: str
    content_type: str
    width: int | None
    height: int | None
    bytes: int


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    message_type: MessageType
    body: str | None
    client_id: str | None
    attachments: list[AttachmentRead]
    created_at: datetime


class ConversationRead(BaseModel):
    id: int
    counterpart: Counterpart
    last_message: MessageRead | None
    last_message_at: datetime | None
    unread_count: int


class MessageCreate(BaseModel):
    body: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    client_id: ClientId = None


class MarkReadRequest(BaseModel):
    message_id: int


class MessagePage(BaseModel):
    items: list[MessageRead]
    has_more: bool


class UnreadCount(BaseModel):
    unread: int
