from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentPatient, CurrentUser, DbSession, PatientUser
from app.core.pagination import Pagination
from app.core.timeutils import utcnow
from app.models import AppointmentStatus, Role
from app.schemas.appointment import (
    AppointmentCreate,
    AppointmentRead,
    CancelRequest,
    CompleteRequest,
)
from app.schemas.common import Page, error_responses
from app.services import appointment_service
from app.services.appointment_service import Scope

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.post(
    "",
    response_model=AppointmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book an appointment (patients)",
    description=(
        "`starts_at` must be exactly one of the doctor's available slots (see "
        "`GET /doctors/{id}/slots`). Double booking is prevented by a database "
        "constraint: concurrent requests for the same slot yield one 201 and one 409."
    ),
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
async def book(
    body: AppointmentCreate,
    request: Request,
    patient: CurrentPatient,
    user: PatientUser,
    db: DbSession,
) -> AppointmentRead:
    appointment = await appointment_service.book(
        db,
        patient,
        user,
        doctor_id=body.doctor_id,
        starts_at=body.starts_at,
        reason=body.reason,
        request=request,
    )
    return appointment_service.to_read(appointment, user)


@router.get(
    "",
    response_model=Page[AppointmentRead],
    summary="List appointments",
    description=(
        "Scoped by role: patients see their own, doctors see theirs, admins see all "
        "(and may filter by doctor_id / patient_id). `date_from`/`date_to` are clinic-local dates."
    ),
    responses=error_responses(401, 403),
)
async def list_appointments(
    user: CurrentUser,
    db: DbSession,
    page: Pagination,
    scope: Scope = "all",
    status_filter: Annotated[AppointmentStatus | None, Query(alias="status")] = None,
    date_from: date | None = None,
    date_to: date | None = None,
    doctor_id: int | None = None,
    patient_id: int | None = None,
) -> Page[AppointmentRead]:
    if user.role != Role.ADMIN:
        doctor_id = doctor_id if user.role == Role.PATIENT else None
        patient_id = patient_id if user.role == Role.DOCTOR else None
    items, total = await appointment_service.list_for_user(
        db,
        user,
        page,
        scope=scope,
        status=status_filter,
        date_from=date_from,
        date_to=date_to,
        doctor_id=doctor_id,
        patient_id=patient_id,
    )
    now = utcnow()
    return Page[AppointmentRead].build(
        [appointment_service.to_read(a, user, now) for a in items], total, page.page, page.page_size
    )


@router.get(
    "/{appointment_id}",
    response_model=AppointmentRead,
    summary="Appointment details",
    responses=error_responses(401, 404),
)
async def get_appointment(appointment_id: int, user: CurrentUser, db: DbSession) -> AppointmentRead:
    appointment = await appointment_service.get_for_user(db, appointment_id, user)
    return appointment_service.to_read(appointment, user)


@router.post(
    "/{appointment_id}/cancel",
    response_model=AppointmentRead,
    summary="Cancel an appointment",
    description=(
        "Patients may cancel their own appointments up to CANCELLATION_CUTOFF_HOURS before "
        "the start; doctors and admins may cancel until the appointment ends."
    ),
    responses=error_responses(400, 401, 403, 404, 409),
)
async def cancel(
    appointment_id: int, body: CancelRequest, request: Request, user: CurrentUser, db: DbSession
) -> AppointmentRead:
    appointment = await appointment_service.get_for_user(db, appointment_id, user)
    updated = await appointment_service.perform_action(
        db, appointment, user, "cancel", reason=body.reason, request=request
    )
    return appointment_service.to_read(updated, user)


@router.post(
    "/{appointment_id}/confirm",
    response_model=AppointmentRead,
    summary="Confirm a booked appointment (doctor/admin)",
    responses=error_responses(400, 401, 403, 404, 409),
)
async def confirm(
    appointment_id: int, request: Request, user: CurrentUser, db: DbSession
) -> AppointmentRead:
    appointment = await appointment_service.get_for_user(db, appointment_id, user)
    updated = await appointment_service.perform_action(
        db, appointment, user, "confirm", request=request
    )
    return appointment_service.to_read(updated, user)


@router.post(
    "/{appointment_id}/complete",
    response_model=AppointmentRead,
    summary="Mark a confirmed appointment completed (doctor/admin)",
    responses=error_responses(400, 401, 403, 404, 409),
)
async def complete(
    appointment_id: int,
    body: CompleteRequest,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> AppointmentRead:
    appointment = await appointment_service.get_for_user(db, appointment_id, user)
    updated = await appointment_service.perform_action(
        db, appointment, user, "complete", doctor_notes=body.doctor_notes, request=request
    )
    return appointment_service.to_read(updated, user)


@router.post(
    "/{appointment_id}/no-show",
    response_model=AppointmentRead,
    summary="Mark a confirmed appointment as no-show (doctor/admin)",
    responses=error_responses(400, 401, 403, 404, 409),
)
async def no_show(
    appointment_id: int, request: Request, user: CurrentUser, db: DbSession
) -> AppointmentRead:
    appointment = await appointment_service.get_for_user(db, appointment_id, user)
    updated = await appointment_service.perform_action(
        db, appointment, user, "no_show", request=request
    )
    return appointment_service.to_read(updated, user)
