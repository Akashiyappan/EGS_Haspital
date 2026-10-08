"""Read-only doctor tools. Each delegates to a domain service and returns only
public, non-contact information that patients are already allowed to see."""

import datetime as dt
from datetime import timedelta
from typing import Any

from pydantic import BaseModel, Field

from app.ai.tools.base import Tool, ToolContext, ToolError
from app.core.config import settings
from app.core.pagination import PageParams
from app.core.timeutils import clinic_today
from app.models import Doctor
from app.services import doctor_service, slot_service, specialization_service


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
        "List the free appointment start times for a doctor on one date "
        "(clinic-local times). Patients book in the app; you cannot book."
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
        return {
            "doctor_id": doctor.id,
            "date": params.date.isoformat(),
            "timezone": settings.CLINIC_TIMEZONE,
            "free_start_times": [s.starts_at.astimezone(tz).strftime("%H:%M") for s in free],
        }


def default_tools() -> list[Tool]:
    return [
        ListSpecializationsTool(),
        SearchDoctorsBySpecializationTool(),
        GetDoctorProfileTool(),
        GetDoctorAvailabilityTool(),
        GetAvailableAppointmentSlotsTool(),
    ]
