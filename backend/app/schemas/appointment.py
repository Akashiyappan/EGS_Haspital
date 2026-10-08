from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints, field_validator

from app.models.enums import AppointmentStatus

AppointmentAction = Literal["confirm", "cancel", "complete", "no_show"]


class AppointmentCreate(BaseModel):
    doctor_id: int
    starts_at: datetime
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=1000)] = None

    @field_validator("starts_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("starts_at must include a timezone offset (use UTC)")
        return value


class CancelRequest(BaseModel):
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class CompleteRequest(BaseModel):
    doctor_notes: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=4000)
    ] = None


class DoctorBrief(BaseModel):
    id: int
    full_name: str
    avatar_url: str | None
    specializations: list[str]


class PatientBrief(BaseModel):
    id: int
    full_name: str
    avatar_url: str | None


class AppointmentRead(BaseModel):
    id: int
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus
    reason: str | None
    doctor_notes: str | None
    cancellation_reason: str | None
    cancelled_at: datetime | None
    created_at: datetime
    doctor: DoctorBrief
    patient: PatientBrief
    # Actions the current user may take right now; computed server-side so the
    # UI never re-implements authorization or the state machine.
    allowed_actions: list[AppointmentAction]
