from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentDoctor, DbSession
from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.core.pagination import Pagination
from app.models import Patient
from app.schemas.common import Page, error_responses
from app.schemas.doctor import (
    DoctorAdminRead,
    DoctorSelfUpdate,
    ScheduleRuleRead,
    TimeOffRead,
)
from app.services import appointment_service, doctor_service, schedule_service

router = APIRouter(prefix="/doctor", tags=["doctor portal"])


class DoctorScheduleView(BaseModel):
    timezone: str
    rules: list[ScheduleRuleRead]
    time_off: list[TimeOffRead]


class DoctorPatientRead(BaseModel):
    """Minimum necessary patient details for the treating doctor."""

    id: int
    first_name: str
    last_name: str | None
    full_name: str
    email: str
    phone: str | None
    avatar_url: str | None
    date_of_birth: date | None
    gender: str | None
    last_appointment_at: datetime | None = None
    appointment_count: int | None = None


def _patient_read(
    patient: Patient, last_at: datetime | None = None, visits: int | None = None
) -> DoctorPatientRead:
    user = patient.user
    return DoctorPatientRead(
        id=patient.id,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        avatar_url=user.avatar_url,
        date_of_birth=patient.date_of_birth,
        gender=patient.gender,
        last_appointment_at=last_at,
        appointment_count=visits,
    )


@router.get(
    "/me",
    response_model=DoctorAdminRead,
    summary="Own doctor profile",
    responses=error_responses(401, 403),
)
async def get_profile(doctor: CurrentDoctor, db: DbSession) -> DoctorAdminRead:
    return doctor_service.to_admin(await doctor_service.get_doctor(db, doctor.id, public=False))


@router.patch(
    "/me",
    response_model=DoctorAdminRead,
    summary="Update own bio/qualification",
    description="Name, phone and avatar are managed via /users/me; specializations by admins.",
    responses=error_responses(401, 403, 422),
)
async def update_profile(
    body: DoctorSelfUpdate, doctor: CurrentDoctor, db: DbSession
) -> DoctorAdminRead:
    changes = body.model_dump(exclude_unset=True)
    for field in ("bio", "qualification"):
        if field in changes:
            setattr(doctor, field, changes[field])
    await db.commit()
    return doctor_service.to_admin(await doctor_service.get_doctor(db, doctor.id, public=False))


@router.get(
    "/schedule",
    response_model=DoctorScheduleView,
    summary="Own weekly schedule and upcoming time off (read-only)",
    responses=error_responses(401, 403),
)
async def my_schedule(doctor: CurrentDoctor, db: DbSession) -> DoctorScheduleView:
    rules = await schedule_service.get_rules(db, doctor.id)
    time_off = await schedule_service.list_time_off(db, doctor.id)
    return DoctorScheduleView(
        timezone=settings.CLINIC_TIMEZONE,
        rules=[ScheduleRuleRead.model_validate(r) for r in rules],
        time_off=[TimeOffRead.model_validate(t) for t in time_off],
    )


@router.get(
    "/patients",
    response_model=Page[DoctorPatientRead],
    summary="Patients with appointments with me",
    responses=error_responses(401, 403),
)
async def my_patients(
    doctor: CurrentDoctor,
    db: DbSession,
    page: Pagination,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> Page[DoctorPatientRead]:
    rows, total = await appointment_service.doctor_patients(db, doctor, page, search)
    return Page[DoctorPatientRead].build(
        [_patient_read(p, last_at, visits) for p, last_at, visits in rows],
        total,
        page.page,
        page.page_size,
    )


@router.get(
    "/patients/{patient_id}",
    response_model=DoctorPatientRead,
    summary="Patient details (only for my patients)",
    responses=error_responses(401, 403, 404),
)
async def patient_detail(
    patient_id: int, doctor: CurrentDoctor, db: DbSession
) -> DoctorPatientRead:
    if not await appointment_service.doctor_has_patient(db, doctor.id, patient_id):
        raise NotFoundError("Patient not found")
    patient = await db.get(Patient, patient_id)
    if patient is None:
        raise NotFoundError("Patient not found")
    return _patient_read(patient)
