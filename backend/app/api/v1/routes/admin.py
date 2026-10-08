from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy import func, select

from app.api.deps import AdminUser, DbSession, user_rate_limit
from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.pagination import Pagination
from app.core.timeutils import clinic_day_bounds_utc, clinic_today, utcnow
from app.integrations.storage import ImageStorage, get_storage, read_validated_image
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    AuditLog,
    Doctor,
    Role,
    User,
)
from app.schemas.common import Page, error_responses
from app.schemas.doctor import (
    DoctorAdminRead,
    DoctorCreate,
    DoctorPasswordReset,
    DoctorStatusResult,
    DoctorStatusUpdate,
    DoctorUpdate,
    ScheduleChangeResult,
    ScheduleRead,
    ScheduleReplace,
    ScheduleRuleRead,
    SpecializationCreate,
    SpecializationRead,
    SpecializationUpdate,
    TimeOffCreate,
    TimeOffRead,
    TimeOffResult,
)
from app.schemas.notification import AdminStats, AuditLogRead
from app.schemas.user import AdminUserRead, UserStatusUpdate
from app.services import (
    audit_service,
    doctor_service,
    schedule_service,
    specialization_service,
    user_service,
)
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/admin", tags=["admin"])

_ADMIN_ERRORS = error_responses(401, 403, 404, 422)


# --- Doctors ---------------------------------------------------------------------


@router.get(
    "/doctors",
    response_model=Page[DoctorAdminRead],
    summary="List doctors (all statuses)",
    responses=_ADMIN_ERRORS,
)
async def list_doctors(
    _: AdminUser,
    db: DbSession,
    page: Pagination,
    search: Annotated[str | None, Query(max_length=100)] = None,
    specialization_id: int | None = None,
    is_active: bool | None = None,
) -> Page[DoctorAdminRead]:
    doctors, total = await doctor_service.list_doctors(
        db,
        page,
        public=False,
        search=search,
        specialization_id=specialization_id,
        is_active=is_active,
    )
    return Page[DoctorAdminRead].build(
        [doctor_service.to_admin(d) for d in doctors], total, page.page, page.page_size
    )


@router.post(
    "/doctors",
    response_model=DoctorAdminRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a doctor account",
    description=(
        "Creates the login and profile. The temporary password is never returned; the "
        "doctor must change it at first login."
    ),
    responses=error_responses(400, 401, 403, 409, 422),
)
async def create_doctor(
    body: DoctorCreate, request: Request, admin: AdminUser, db: DbSession
) -> DoctorAdminRead:
    doctor = await doctor_service.create_doctor(db, body, admin, request)
    return doctor_service.to_admin(doctor)


@router.get(
    "/doctors/{doctor_id}",
    response_model=DoctorAdminRead,
    summary="Doctor details",
    responses=_ADMIN_ERRORS,
)
async def get_doctor(doctor_id: int, _: AdminUser, db: DbSession) -> DoctorAdminRead:
    return doctor_service.to_admin(await doctor_service.get_doctor(db, doctor_id, public=False))


@router.patch(
    "/doctors/{doctor_id}",
    response_model=DoctorAdminRead,
    summary="Update a doctor",
    responses=error_responses(400, 401, 403, 404, 422),
)
async def update_doctor(
    doctor_id: int, body: DoctorUpdate, request: Request, admin: AdminUser, db: DbSession
) -> DoctorAdminRead:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    updated = await doctor_service.update_doctor(db, doctor, body, admin, request)
    return doctor_service.to_admin(updated)


@router.post(
    "/doctors/{doctor_id}/status",
    response_model=DoctorStatusResult,
    summary="Activate or deactivate a doctor",
    description=(
        "Deactivation signs the doctor out and cancels their upcoming appointments; "
        "affected patients are notified."
    ),
    responses=_ADMIN_ERRORS,
)
async def set_doctor_status(
    doctor_id: int, body: DoctorStatusUpdate, request: Request, admin: AdminUser, db: DbSession
) -> DoctorStatusResult:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    cancelled = await doctor_service.set_active(
        db, doctor, body.is_active, admin, request, body.reason
    )
    refreshed = await doctor_service.get_doctor(db, doctor_id, public=False)
    return DoctorStatusResult(
        doctor=doctor_service.to_admin(refreshed), cancelled_appointments=cancelled
    )


@router.delete(
    "/doctors/{doctor_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a doctor (soft delete)",
    description="History is retained; the account can no longer sign in or be booked.",
    responses=_ADMIN_ERRORS,
)
async def delete_doctor(doctor_id: int, request: Request, admin: AdminUser, db: DbSession) -> None:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    await doctor_service.soft_delete(db, doctor, admin, request)


@router.post(
    "/doctors/{doctor_id}/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Issue a new temporary password",
    description="Signs the doctor out; they must change the password at next login.",
    responses=_ADMIN_ERRORS,
)
async def reset_doctor_password(
    doctor_id: int, body: DoctorPasswordReset, request: Request, admin: AdminUser, db: DbSession
) -> None:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    await doctor_service.reset_password(db, doctor, body.temporary_password, admin, request)


@router.post(
    "/doctors/{doctor_id}/avatar",
    response_model=DoctorAdminRead,
    summary="Upload a doctor's profile image",
    responses=error_responses(400, 401, 403, 404, 413, 429, 503),
    dependencies=[Depends(user_rate_limit("upload", settings.RATE_LIMIT_UPLOAD))],
)
async def upload_doctor_avatar(
    doctor_id: int,
    _: AdminUser,
    db: DbSession,
    storage: Annotated[ImageStorage, Depends(get_storage)],
    file: Annotated[UploadFile, File()],
) -> DoctorAdminRead:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    data, content_type = await read_validated_image(file)
    image = await storage.upload_image(
        data, folder="avatars", content_type=content_type, private=False
    )
    previous = doctor.user.avatar_public_id
    doctor.user.avatar_url, doctor.user.avatar_public_id = image.url, image.public_id
    await db.commit()
    if previous:
        await storage.delete(previous, "upload")
    return doctor_service.to_admin(doctor)


# --- Schedules & time off --------------------------------------------------------


@router.get(
    "/doctors/{doctor_id}/schedule",
    response_model=ScheduleRead,
    summary="Doctor's weekly schedule",
    responses=_ADMIN_ERRORS,
)
async def get_schedule(doctor_id: int, _: AdminUser, db: DbSession) -> ScheduleRead:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    rules = await schedule_service.get_rules(db, doctor.id)
    return ScheduleRead(
        timezone=settings.CLINIC_TIMEZONE,
        rules=[ScheduleRuleRead.model_validate(r) for r in rules],
    )


@router.put(
    "/doctors/{doctor_id}/schedule",
    response_model=ScheduleChangeResult,
    summary="Replace a doctor's weekly schedule",
    description=(
        "Wall-clock times in the clinic timezone. Several periods per weekday are allowed "
        "(they must not overlap). Existing appointments are never cancelled automatically; "
        "upcoming ones that no longer fit are listed in `conflicting_appointment_ids`."
    ),
    responses=error_responses(400, 401, 403, 404, 422),
)
async def replace_schedule(
    doctor_id: int, body: ScheduleReplace, request: Request, admin: AdminUser, db: DbSession
) -> ScheduleChangeResult:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    rules, conflicts = await schedule_service.replace_rules(db, doctor, body.rules, admin, request)
    return ScheduleChangeResult(
        timezone=settings.CLINIC_TIMEZONE,
        rules=[ScheduleRuleRead.model_validate(r) for r in rules],
        conflicting_appointment_ids=conflicts,
    )


@router.get(
    "/doctors/{doctor_id}/time-off",
    response_model=list[TimeOffRead],
    summary="Doctor's current and upcoming time off (incl. clinic holidays)",
    responses=_ADMIN_ERRORS,
)
async def list_doctor_time_off(doctor_id: int, _: AdminUser, db: DbSession) -> list[TimeOffRead]:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    entries = await schedule_service.list_time_off(db, doctor.id)
    return [TimeOffRead.model_validate(e) for e in entries]


@router.post(
    "/doctors/{doctor_id}/time-off",
    response_model=TimeOffResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add leave or unavailability for a doctor",
    responses=error_responses(400, 401, 403, 404, 422),
)
async def add_doctor_time_off(
    doctor_id: int, body: TimeOffCreate, request: Request, admin: AdminUser, db: DbSession
) -> TimeOffResult:
    doctor = await doctor_service.get_doctor(db, doctor_id, public=False)
    entry, conflicts = await schedule_service.add_time_off(db, doctor, body, admin, request)
    return TimeOffResult(
        **TimeOffRead.model_validate(entry).model_dump(), conflicting_appointment_ids=conflicts
    )


@router.get(
    "/time-off",
    response_model=list[TimeOffRead],
    summary="Clinic-wide holidays",
    responses=_ADMIN_ERRORS,
)
async def list_clinic_time_off(_: AdminUser, db: DbSession) -> list[TimeOffRead]:
    entries = await schedule_service.list_time_off(db, None)
    return [TimeOffRead.model_validate(e) for e in entries]


@router.post(
    "/time-off",
    response_model=TimeOffResult,
    status_code=status.HTTP_201_CREATED,
    summary="Add a clinic-wide holiday (blocks every doctor)",
    responses=error_responses(400, 401, 403, 422),
)
async def add_clinic_time_off(
    body: TimeOffCreate, request: Request, admin: AdminUser, db: DbSession
) -> TimeOffResult:
    entry, conflicts = await schedule_service.add_time_off(db, None, body, admin, request)
    return TimeOffResult(
        **TimeOffRead.model_validate(entry).model_dump(), conflicting_appointment_ids=conflicts
    )


@router.delete(
    "/time-off/{time_off_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a time-off entry",
    responses=_ADMIN_ERRORS,
)
async def delete_time_off(
    time_off_id: int, request: Request, admin: AdminUser, db: DbSession
) -> None:
    await schedule_service.remove_time_off(db, time_off_id, admin, request)


# --- Specializations -------------------------------------------------------------


@router.get(
    "/specializations",
    response_model=list[SpecializationRead],
    summary="All specializations (incl. inactive)",
    responses=_ADMIN_ERRORS,
)
async def list_specializations(_: AdminUser, db: DbSession) -> list[SpecializationRead]:
    items = await specialization_service.list_specializations(db, active_only=False)
    return [SpecializationRead.model_validate(s) for s in items]


@router.post(
    "/specializations",
    response_model=SpecializationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a specialization",
    responses=error_responses(401, 403, 409, 422),
)
async def create_specialization(
    body: SpecializationCreate, request: Request, admin: AdminUser, db: DbSession
) -> SpecializationRead:
    specialization = await specialization_service.create(db, body)
    audit_service.record(
        db,
        AuditAction.SPECIALIZATION_CREATED,
        actor_id=admin.id,
        entity_type="specialization",
        entity_id=specialization.id,
        details={"name": specialization.name},
        request=request,
    )
    await db.commit()
    return SpecializationRead.model_validate(specialization)


@router.patch(
    "/specializations/{specialization_id}",
    response_model=SpecializationRead,
    summary="Update or (de)activate a specialization",
    responses=error_responses(401, 403, 404, 409, 422),
)
async def update_specialization(
    specialization_id: int,
    body: SpecializationUpdate,
    request: Request,
    admin: AdminUser,
    db: DbSession,
) -> SpecializationRead:
    specialization = await specialization_service.get(db, specialization_id)
    await specialization_service.update(db, specialization, body)
    audit_service.record(
        db,
        AuditAction.SPECIALIZATION_UPDATED,
        actor_id=admin.id,
        entity_type="specialization",
        entity_id=specialization.id,
        details={"fields": sorted(body.model_dump(exclude_unset=True))},
        request=request,
    )
    await db.commit()
    return SpecializationRead.model_validate(specialization)


# --- Users -----------------------------------------------------------------------


@router.get(
    "/users",
    response_model=Page[AdminUserRead],
    summary="List users",
    responses=_ADMIN_ERRORS,
)
async def list_users(
    _: AdminUser,
    db: DbSession,
    page: Pagination,
    role: Role | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: bool | None = None,
) -> Page[AdminUserRead]:
    users, total = await user_service.list_users(
        db, page, role=role, search=search, is_active=is_active
    )
    return Page[AdminUserRead].build(
        [AdminUserRead.model_validate(u) for u in users], total, page.page, page.page_size
    )


@router.post(
    "/users/{user_id}/status",
    response_model=AdminUserRead,
    summary="Activate or deactivate a patient/admin account",
    description="Use the doctor endpoints for doctors. Admins cannot deactivate themselves.",
    responses=error_responses(400, 401, 403, 404, 422),
)
async def set_user_status(
    user_id: int, body: UserStatusUpdate, request: Request, admin: AdminUser, db: DbSession
) -> AdminUserRead:
    user = await db.get(User, user_id)
    if user is None or user.deleted_at is not None:
        raise NotFoundError("User not found")
    if user.role == Role.DOCTOR:
        raise AppError("Use the doctor status endpoint for doctors", code="use_doctor_endpoint")
    if user.id == admin.id:
        raise AppError("You cannot change your own status", code="self_status_change")
    if user.is_active and not body.is_active:
        user.token_version += 1
    user.is_active = body.is_active
    audit_service.record(
        db,
        AuditAction.USER_ACTIVATED if body.is_active else AuditAction.USER_DEACTIVATED,
        actor_id=admin.id,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    return AdminUserRead.model_validate(user)


# --- Overview --------------------------------------------------------------------


@router.get(
    "/stats", response_model=AdminStats, summary="Dashboard counters", responses=_ADMIN_ERRORS
)
async def stats(_: AdminUser, db: DbSession) -> AdminStats:
    now = utcnow()
    today_start, today_end = clinic_day_bounds_utc(clinic_today(now))

    doctor_counts: dict[bool, int] = dict(
        (
            await db.execute(
                select(User.is_active, func.count())
                .select_from(Doctor)
                .join(User, Doctor.user_id == User.id)
                .where(User.deleted_at.is_(None))
                .group_by(User.is_active)
            )
        )
        .tuples()
        .all()
    )
    patients = await db.scalar(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.PATIENT, User.deleted_at.is_(None))
    )
    active = Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)
    today = await db.scalar(
        select(func.count())
        .select_from(Appointment)
        .where(active, Appointment.starts_at >= today_start, Appointment.starts_at < today_end)
    )
    upcoming = await db.scalar(
        select(func.count()).select_from(Appointment).where(active, Appointment.starts_at >= now)
    )
    by_status: dict[AppointmentStatus, int] = dict(
        (
            await db.execute(
                select(Appointment.status, func.count())
                .where(Appointment.starts_at >= now - timedelta(days=30))
                .group_by(Appointment.status)
            )
        )
        .tuples()
        .all()
    )
    return AdminStats(
        doctors_active=doctor_counts.get(True, 0),
        doctors_inactive=doctor_counts.get(False, 0),
        patients=patients or 0,
        appointments_today=today or 0,
        appointments_upcoming=upcoming or 0,
        appointments_by_status={str(k): v for k, v in by_status.items()},
    )


@router.get(
    "/audit-logs",
    response_model=Page[AuditLogRead],
    summary="Audit log",
    responses=_ADMIN_ERRORS,
)
async def audit_logs(
    _: AdminUser,
    db: DbSession,
    page: Pagination,
    action: Annotated[str | None, Query(max_length=64)] = None,
    actor_id: int | None = None,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    since: date | None = None,
) -> Page[AuditLogRead]:
    query = select(AuditLog)
    if action:
        query = query.where(AuditLog.action == action)
    if actor_id is not None:
        query = query.where(AuditLog.actor_id == actor_id)
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if since:
        query = query.where(AuditLog.created_at >= clinic_day_bounds_utc(since)[0])
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(AuditLog.id.desc()).limit(page.page_size).offset(page.offset)
    )
    return Page[AuditLogRead].build(
        [AuditLogRead.model_validate(r) for r in rows], total, page.page, page.page_size
    )
