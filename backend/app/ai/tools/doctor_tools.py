"""Hospital data retrieval and appointment actions for the patient assistant."""

import datetime as dt
import re
from datetime import timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.ai.safety import has_red_flags
from app.ai.tools.base import Tool, ToolContext, ToolError
from app.core.config import settings
from app.core.pagination import PageParams
from app.core.timeutils import clinic_today
from app.models import Doctor
from app.services import appointment_service, doctor_service, slot_service, specialization_service


def _doctor_summary(doctor: Doctor) -> dict[str, Any]:
    return {
        "doctor_id": doctor.id,
        "name": f"Dr. {doctor.user.full_name}",
        "specializations": [s.name for s in doctor.specializations],
        "qualification": doctor.qualification,
        "experience_years": doctor.experience_years,
    }


class _NoParams(BaseModel):
    pass


class ListSpecializationsTool(Tool):
    name = "list_specializations"
    description = (
        "List the medical specializations available at this hospital, with short "
        "descriptions. Use it to pick the exact specialization name to search for."
    )
    Params = _NoParams

    async def run(self, ctx: ToolContext, params: Any) -> dict[str, Any]:
        items = await specialization_service.list_specializations(ctx.db, active_only=True)
        return {
            "specializations": [{"name": s.name, "description": s.description or ""} for s in items]
        }


class SearchDoctorsParams(BaseModel):
    specialization: str = Field(
        min_length=2, max_length=100, description="Specialization name, e.g. 'Cardiology'."
    )
    limit: int = Field(default=5, ge=1, le=10)


class SearchDoctorsBySpecializationTool(Tool):
    name = "search_doctors_by_specialization"
    description = (
        "Find active doctors at this hospital who practise a given specialization. "
        "Returns doctor_id, name, specializations, qualification and experience. "
        "These are the only doctors you may recommend."
    )
    Params = SearchDoctorsParams

    async def run(self, ctx: ToolContext, params: SearchDoctorsParams) -> dict[str, Any]:
        wanted = params.specialization.strip().lower()
        specializations = await specialization_service.list_specializations(
            ctx.db, active_only=True
        )
        match = next((s for s in specializations if s.name.lower() == wanted), None) or next(
            (s for s in specializations if wanted in s.name.lower() or s.name.lower() in wanted),
            None,
        )
        if match is None:
            return {
                "matched_specialization": None,
                "doctors": [],
                "available_specializations": [s.name for s in specializations],
            }
        doctors, _ = await doctor_service.list_doctors(
            ctx.db,
            PageParams(page=1, page_size=params.limit),
            public=True,
            specialization_id=match.id,
        )
        ctx.seen_doctor_ids.update(d.id for d in doctors)
        return {
            "matched_specialization": match.name,
            "doctors": [_doctor_summary(d) for d in doctors],
        }


class DoctorIdParams(BaseModel):
    doctor_id: int = Field(ge=1)


class GetDoctorProfileTool(Tool):
    name = "get_doctor_profile"
    description = (
        "Get the public profile of one doctor by doctor_id (bio, qualification, experience)."
    )
    Params = DoctorIdParams

    async def run(self, ctx: ToolContext, params: DoctorIdParams) -> dict[str, Any]:
        doctor = await doctor_service.get_doctor(ctx.db, params.doctor_id, public=True)
        ctx.seen_doctor_ids.add(doctor.id)
        return {**_doctor_summary(doctor), "bio": (doctor.bio or "")[:600]}


class AvailabilityParams(BaseModel):
    doctor_id: int = Field(ge=1)
    days: int = Field(default=7, ge=1, le=14, description="How many days ahead to check.")


class GetDoctorAvailabilityTool(Tool):
    name = "get_doctor_availability"
    description = (
        "Count a doctor's free appointment slots per day for the next N days "
        f"(dates in the clinic timezone, {settings.CLINIC_TIMEZONE})."
    )
    Params = AvailabilityParams

    async def run(self, ctx: ToolContext, params: AvailabilityParams) -> dict[str, Any]:
        doctor = await doctor_service.get_doctor(ctx.db, params.doctor_id, public=True)
        ctx.seen_doctor_ids.add(doctor.id)
        first = clinic_today(ctx.now)
        days = await slot_service.slots_for_range(
            ctx.db, doctor.id, first, first + timedelta(days=params.days - 1), ctx.now
        )
        return {
            "doctor_id": doctor.id,
            "timezone": settings.CLINIC_TIMEZONE,
            "days": [
                {"date": day.isoformat(), "free_slots": sum(s.available for s in slots)}
                for day, slots in days.items()
            ],
        }


class SlotsParams(BaseModel):
    doctor_id: int = Field(ge=1)
    date: dt.date = Field(description="Clinic-local date, YYYY-MM-DD.")


class GetAvailableAppointmentSlotsTool(Tool):
    name = "get_available_appointment_slots"
    description = (
        "Retrieve the real free appointment slots for a doctor on one date. "
        "Always call this before offering or booking a slot."
    )
    Params = SlotsParams

    async def run(self, ctx: ToolContext, params: SlotsParams) -> dict[str, Any]:
        doctor = await doctor_service.get_doctor(ctx.db, params.doctor_id, public=True)
        ctx.seen_doctor_ids.add(doctor.id)
        if params.date < clinic_today(ctx.now):
            raise ToolError("That date is in the past")
        days = await slot_service.slots_for_range(
            ctx.db, doctor.id, params.date, params.date, ctx.now
        )
        tz = settings.clinic_tz
        free = [s for s in days.get(params.date, []) if s.available]
        slots = [
            {
                "starts_at": slot.starts_at.isoformat(),
                "local_time": slot.starts_at.astimezone(tz).strftime("%H:%M"),
            }
            for slot in free
        ]
        ctx.available_slots.update(
            (doctor.id, slot.starts_at.astimezone(timezone.utc).isoformat()) for slot in free
        )
        specialization = doctor.specializations[0].name if doctor.specializations else "General Medicine"
        ctx.appointment_options.extend(
            {
                "doctor_id": doctor.id,
                "doctor_name": f"Dr. {doctor.user.full_name}",
                "specialization": specialization,
                "starts_at": slot.starts_at.isoformat(),
                "local_time": slot.starts_at.astimezone(tz).strftime("%H:%M"),
            }
            for slot in free
        )
        return {
            "doctor_id": doctor.id,
            "date": params.date.isoformat(),
            "timezone": settings.CLINIC_TIMEZONE,
            "free_start_times": [s["local_time"] for s in slots],
            "available_slots": slots,
        }


class BookAppointmentParams(BaseModel):
    doctor_id: int = Field(ge=1)
    starts_at: dt.datetime = Field(
        description="The exact ISO-8601 starts_at value returned by get_available_appointment_slots."
    )

    @field_validator("starts_at")
    @classmethod
    def require_timezone(cls, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            raise ValueError("starts_at must include a timezone offset")
        return value


class BookAppointmentTool(Tool):
    name = "book_appointment"
    description = (
        "Book an appointment for the signed-in patient. Use only after the patient clearly "
        "asks to book a specific doctor and time. First retrieve that date's live slots with "
        "get_available_appointment_slots and pass its exact starts_at value. Never book based "
        "on a question, an implied preference, or a time that was not returned as available."
    )
    Params = BookAppointmentParams

    async def run(self, ctx: ToolContext, params: BookAppointmentParams) -> dict[str, Any]:
        if ctx.patient is None or ctx.patient_user is None:
            raise ToolError("Booking is available to signed-in patients only.")
        if has_red_flags(ctx.current_text):
            raise ToolError("Do not book a routine slot for possible emergency symptoms; direct the patient to emergency care.")
        text = ctx.current_text.lower()
        if not re.search(r"\b(book|schedule|reserve|confirm)\b", text) or re.search(
            r"\b(don't|do not|not|never|cancel)\b.{0,30}\b(book|schedule|reserve|confirm)\b",
            text,
        ):
            raise ToolError("The patient's latest message does not explicitly authorize booking.")
        selected_slot = re.search(r"\b(it|that slot|that time|this slot|this time)\b", text)
        explicit_time = re.search(
            r"\b(?:at\s*)?(?:(\d{1,2}):(\d{2})|(?:(\d{1,2})\s*(am|pm)))\b",
            text,
        )
        if explicit_time:
            hour = int(explicit_time.group(1) or explicit_time.group(3))
            minute = int(explicit_time.group(2) or 0)
            suffix = explicit_time.group(4)
            if suffix:
                hour = hour % 12 + (12 if suffix == "pm" else 0)
            requested_time = f"{hour:02d}:{minute:02d}"
            slot_time = params.starts_at.astimezone(settings.clinic_tz).strftime("%H:%M")
            if requested_time != slot_time:
                raise ToolError("The selected time does not match the time the patient requested.")
        if not selected_slot and not explicit_time:
            raise ToolError(
                "The patient has not selected a specific slot yet. Offer available times and ask which one they want."
            )
        key = (params.doctor_id, params.starts_at.astimezone(timezone.utc).isoformat())
        if key not in ctx.available_slots:
            raise ToolError("That exact slot was not freshly retrieved as available. Check the date's slots first.")

        appointment = await appointment_service.book(
            ctx.db,
            ctx.patient,
            ctx.patient_user,
            doctor_id=params.doctor_id,
            starts_at=params.starts_at,
            reason=None,
        )
        confirmation = {
            "id": appointment.id,
            "doctor_id": appointment.doctor_id,
            "doctor_name": f"Dr. {appointment.doctor.user.full_name}",
            "starts_at": appointment.starts_at.isoformat(),
            "status": appointment.status.value,
        }
        ctx.booked_appointment = confirmation
        ctx.appointment_options = [
            option
            for option in ctx.appointment_options
            if not (
                option["doctor_id"] == params.doctor_id
                and option["starts_at"] == params.starts_at.isoformat()
            )
        ]
        return {"booked": True, "appointment": confirmation}


def default_tools() -> list[Tool]:
    return [
        ListSpecializationsTool(),
        SearchDoctorsBySpecializationTool(),
        GetDoctorProfileTool(),
        GetDoctorAvailabilityTool(),
        GetAvailableAppointmentSlotsTool(),
        BookAppointmentTool(),
    ]
