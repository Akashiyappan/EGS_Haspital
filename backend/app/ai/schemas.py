from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import AIMessageRole
from app.schemas.doctor import DoctorPublic

Urgency = Literal["emergency", "urgent", "routine", "self_care"]
URGENCY_RANK: dict[str, int] = {"self_care": 0, "routine": 1, "urgent": 2, "emergency": 3}

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class AssistantResult(BaseModel):
    """Structured model output after validation and safety post-processing."""

    summary: str = Field(max_length=3000)
    urgency: Urgency = "routine"
    possible_concerns: list[ShortText] = Field(default_factory=list, max_length=5)
    recommended_specializations: list[ShortText] = Field(default_factory=list, max_length=5)
    recommended_doctor_ids: list[int] = Field(default_factory=list, max_length=5)
    next_steps: list[ShortText] = Field(default_factory=list, max_length=5)
    follow_up_questions: list[ShortText] = Field(default_factory=list, max_length=3)
    emergency_message: str | None = None
    disclaimer: str = ""


class AIConversationCreate(BaseModel):
    title: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=200)] = None


class AIConversationRead(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class AIMessageCreate(BaseModel):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]


class AIResultRead(AssistantResult):
    recommended_doctors: list[DoctorPublic] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)


class AIMessageRead(BaseModel):
    id: int
    role: AIMessageRole
    content: str
    result: AIResultRead | None
    created_at: datetime


class AIExchangeRead(BaseModel):
    user_message: AIMessageRead
    assistant_message: AIMessageRead
