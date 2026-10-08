from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.pagination import Pagination
from app.core.timeutils import utcnow
from app.schemas.common import Page, error_responses
from app.schemas.doctor import (
    AvailabilityDay,
    AvailabilityRead,
    DaySlotsRead,
    DoctorPublic,
    SlotRead,
    SpecializationRead,
)
from app.services import doctor_service, schedule_service, slot_service, specialization_service

router = APIRouter(tags=["doctors"])


@router.get(
    "/specializations",
    response_model=list[SpecializationRead],
    summary="Active specializations",
    responses=error_responses(401),
)
async def list_specializations(_: CurrentUser, db: DbSession) -> list[SpecializationRead]:
    items = await specialization_service.list_specializations(db, active_only=True)
    return [SpecializationRead.model_validate(s) for s in items]


@router.get(
    "/doctors",
    response_model=Page[DoctorPublic],
    summary="Search active doctors",
    description="Search by name or specialization; filter by specialization id. Paginated.",
    responses=error_responses(401),
)
async def list_doctors(
    _: CurrentUser,
    db: DbSession,
    page: Pagination,
    search: Annotated[str | None, Query(max_length=100)] = None,
    specialization_id: int | None = None,
) -> Page[DoctorPublic]:
    doctors, total = await doctor_service.list_doctors(
        db, page, public=True, search=search, specialization_id=specialization_id
    )
    return Page[DoctorPublic].build(
        [doctor_service.to_public(d) for d in doctors], total, page.page, page.page_size
    )


@router.get(
    "/doctors/{doctor_id}",
    response_model=DoctorPublic,
    summary="Doctor profile",
    responses=error_responses(401, 404),
)
async def get_doctor(doctor_id: int, _: CurrentUser, db: DbSession) -> DoctorPublic:
    return doctor_service.to_public(await doctor_service.get_doctor(db, doctor_id, public=True))


@router.get(
    "/doctors/{doctor_id}/slots",
    response_model=DaySlotsRead,
    summary="Appointment slots for one day",
    description=(
        "Slots generated from the doctor's schedule for a clinic-local date. Booked or "
        "too-soon slots are returned with available=false. Times are UTC."
    ),
    responses=error_responses(401, 404),
)
async def day_slots(
    doctor_id: int, _: CurrentUser, db: DbSession, day: Annotated[date, Query(alias="date")]
) -> DaySlotsRead:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=True)
    slots = (await slot_service.slots_for_range(db, doctor.id, day, day, utcnow())).get(day, [])
    return DaySlotsRead(
        doctor_id=doctor.id,
        date=day,
        timezone=settings.CLINIC_TIMEZONE,
        slots=[
            SlotRead(starts_at=s.starts_at, ends_at=s.ends_at, available=s.available) for s in slots
        ],
    )


@router.get(
    "/doctors/{doctor_id}/availability",
    response_model=AvailabilityRead,
    summary="Free slot counts per day",
    responses=error_responses(401, 404),
)
async def availability(
    doctor_id: int,
    _: CurrentUser,
    db: DbSession,
    start: Annotated[date | None, Query(alias="from")] = None,
    days: Annotated[int, Query(ge=1, le=31)] = 14,
) -> AvailabilityRead:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=True)
    now = utcnow()
    first, last = schedule_service.availability_range(start, days, now)
    by_day = await slot_service.slots_for_range(db, doctor.id, first, last, now)
    return AvailabilityRead(
        doctor_id=doctor.id,
        timezone=settings.CLINIC_TIMEZONE,
        days=[
            AvailabilityDay(date=d, available_slots=sum(s.available for s in slots))
            for d, slots in by_day.items()
        ],
    )
