from datetime import date, datetime, time
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from app.core.config import settings
from app.models.enums import TimeOffKind
from app.schemas.common import ORMModel
from app.schemas.user import NormalizedEmail, OptionalName, Password, PersonName, Phone

Bio = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=2000)]
Qualification = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=255)]


# --- Specializations -------------------------------------------------------------


class SpecializationRead(ORMModel):
    id: int
    name: str
    description: str | None
    is_active: bool


class SpecializationCreate(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    description: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None


class SpecializationUpdate(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
        | None
    ) = None
    description: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=1000)
    ] = None
    is_active: bool | None = None


# --- Doctors ---------------------------------------------------------------------


class DoctorPublic(BaseModel):
    """What patients may see about a doctor (no contact details)."""

    id: int
    first_name: str
    last_name: str | None
    full_name: str
    avatar_url: str | None
    qualification: str | None
    experience_years: int
    bio: str | None
    specializations: list[SpecializationRead]


class DoctorAdminRead(DoctorPublic):
    user_id: int
    email: str
    phone: str | None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


SpecializationIds = Annotated[list[int], Field(min_length=1, max_length=10)]


class DoctorCreate(BaseModel):
    first_name: PersonName
    last_name: OptionalName = None
    email: NormalizedEmail
    temporary_password: Password = Field(
        description="Issued to the doctor out of band; they must change it at first login."
    )
    phone: Phone = None
    specialization_ids: SpecializationIds
    qualification: Qualification = None
    experience_years: int = Field(default=0, ge=0, le=80)
    bio: Bio = None
    is_active: bool = True

    @field_validator("specialization_ids")
    @classmethod
    def _unique(cls, value: list[int]) -> list[int]:
        return sorted(set(value))


class DoctorUpdate(BaseModel):
    first_name: PersonName | None = None
    last_name: OptionalName = None
    phone: Phone = None
    specialization_ids: SpecializationIds | None = None
    qualification: Qualification = None
    experience_years: int | None = Field(default=None, ge=0, le=80)
    bio: Bio = None

    @field_validator("specialization_ids")
    @classmethod
    def _unique(cls, value: list[int] | None) -> list[int] | None:
        return sorted(set(value)) if value is not None else None


class DoctorSelfUpdate(BaseModel):
    """Fields a doctor may edit on their own profile."""

    bio: Bio = None
    qualification: Qualification = None


class DoctorPasswordReset(BaseModel):
    temporary_password: Password


class DoctorStatusUpdate(BaseModel):
    is_active: bool
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=255)] = None


class DoctorStatusResult(BaseModel):
    doctor: DoctorAdminRead
    cancelled_appointments: int


# --- Schedules -------------------------------------------------------------------


class ScheduleRuleIn(BaseModel):
    weekday: int = Field(ge=0, le=6, description="0 = Monday … 6 = Sunday")
    start_time: time
    end_time: time
    slot_minutes: int | None = Field(default=None, ge=5, le=240)
    effective_from: date | None = None
    effective_until: date | None = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.start_time.tzinfo or self.end_time.tzinfo:
            raise ValueError("Schedule times are clinic-local wall-clock times without offset")
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        slot = self.slot_minutes or settings.APPOINTMENT_DURATION_MINUTES
        minutes = (self.end_time.hour * 60 + self.end_time.minute) - (
            self.start_time.hour * 60 + self.start_time.minute
        )
        if minutes < slot:
            raise ValueError(f"A working period must be at least {slot} minutes long")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_until < self.effective_from
        ):
            raise ValueError("effective_until must be on or after effective_from")
        return self


class ScheduleReplace(BaseModel):
    rules: list[ScheduleRuleIn] = Field(max_length=50)


class ScheduleRuleRead(ORMModel):
    id: int
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int
    effective_from: date | None
    effective_until: date | None


class ScheduleRead(BaseModel):
    timezone: str
    rules: list[ScheduleRuleRead]


class ScheduleChangeResult(ScheduleRead):
    # Upcoming appointments that no longer fit the schedule; they are kept and
    # must be handled explicitly by an admin.
    conflicting_appointment_ids: list[int]


class TimeOffCreate(BaseModel):
    kind: TimeOffKind = TimeOffKind.LEAVE
    starts_at: datetime
    ends_at: datetime
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=255)] = None

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("starts_at and ends_at must include a timezone offset")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class TimeOffRead(ORMModel):
    id: int
    doctor_id: int | None
    kind: TimeOffKind
    starts_at: datetime
    ends_at: datetime
    reason: str | None


class TimeOffResult(TimeOffRead):
    conflicting_appointment_ids: list[int]


# --- Slots -----------------------------------------------------------------------


class SlotRead(BaseModel):
    starts_at: datetime
    ends_at: datetime
    available: bool


class DaySlotsRead(BaseModel):
    doctor_id: int
    date: date
    timezone: str
    slots: list[SlotRead]


class AvailabilityDay(BaseModel):
    date: date
    available_slots: int


class AvailabilityRead(BaseModel):
    doctor_id: int
    timezone: str
    days: list[AvailabilityDay]
