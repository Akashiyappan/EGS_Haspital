import logging
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import Request
from sqlalchemy import Select, and_, func, not_, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError, ForbiddenError, NotFoundError
from app.core.pagination import LIKE_ESCAPE, PageParams, escape_like
from app.core.timeutils import clinic_day_bounds_utc, utcnow
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    APPOINTMENT_TRANSITIONS,
    Appointment,
    AppointmentStatus,
    Doctor,
    NotificationType,
    Patient,
    Role,
    User,
)
from app.schemas.appointment import (
    AppointmentAction,
    AppointmentRead,
    DoctorBrief,
    PatientBrief,
)
from app.services import audit_service, slot_service
from app.services.audit_service import AuditAction
from app.services.notification_service import (
    NotificationPayload,
    Notifier,
    format_clinic_time,
)

logger = logging.getLogger(__name__)

ACTION_TARGET: dict[AppointmentAction, AppointmentStatus] = {
    "confirm": AppointmentStatus.CONFIRMED,
    "cancel": AppointmentStatus.CANCELLED,
    "complete": AppointmentStatus.COMPLETED,
    "no_show": AppointmentStatus.NO_SHOW,
}

Scope = Literal["upcoming", "past", "all"]

# MySQL error codes: 1213 = deadlock, 1205 = lock wait timeout.
_LOCK_CONFLICT_CODES = {1213, 1205}


def is_lock_conflict(exc: OperationalError) -> bool:
    args: tuple[object, ...] = tuple(getattr(exc.orig, "args", ()))
    return bool(args) and args[0] in _LOCK_CONFLICT_CODES


def _with_parties(query: Select[tuple[Appointment]]) -> Select[tuple[Appointment]]:
    return query.options(selectinload(Appointment.doctor), selectinload(Appointment.patient))


# --- Authorization & state machine ----------------------------------------------


def check_action(
    appointment: Appointment, user: User, action: AppointmentAction, now: datetime
) -> None:
    """Raise if `user` may not perform `action` now. Ownership is checked by
    the caller (get_for_user) before this runs."""
    target = ACTION_TARGET[action]
    if target not in APPOINTMENT_TRANSITIONS[appointment.status]:
        raise ConflictError(
            f"Cannot {action.replace('_', ' ')} an appointment that is {appointment.status.lower()}",
            code="invalid_transition",
        )
    if user.role == Role.PATIENT:
        if action != "cancel":
            raise ForbiddenError()
        cutoff = timedelta(hours=settings.CANCELLATION_CUTOFF_HOURS)
        if appointment.starts_at - now < cutoff:
            raise AppError(
                f"Appointments can only be cancelled up to {settings.CANCELLATION_CUTOFF_HOURS} "
                "hours before they start",
                code="cancellation_window_closed",
            )
        return
    if user.role in (Role.DOCTOR, Role.ADMIN):
        if action in ("complete", "no_show") and now < appointment.starts_at:
            raise AppError("This appointment has not started yet", code="appointment_not_started")
        if action in ("confirm", "cancel") and now >= appointment.ends_at:
            raise AppError("This appointment is already over", code="appointment_over")
        return
    raise ForbiddenError()


def allowed_actions(appointment: Appointment, user: User, now: datetime) -> list[AppointmentAction]:
    allowed: list[AppointmentAction] = []
    for action in ACTION_TARGET:
        try:
            check_action(appointment, user, action, now)
        except AppError:
            continue
        allowed.append(action)
    return allowed


# --- Serialization ---------------------------------------------------------------


def to_read(appointment: Appointment, viewer: User, now: datetime | None = None) -> AppointmentRead:
    doctor, patient = appointment.doctor, appointment.patient
    return AppointmentRead(
        id=appointment.id,
        starts_at=appointment.starts_at,
        ends_at=appointment.ends_at,
        status=appointment.status,
        reason=appointment.reason,
        doctor_notes=appointment.doctor_notes if viewer.role != Role.PATIENT else None,
        cancellation_reason=appointment.cancellation_reason,
        cancelled_at=appointment.cancelled_at,
        created_at=appointment.created_at,
        doctor=DoctorBrief(
            id=doctor.id,
            full_name=doctor.user.full_name,
            avatar_url=doctor.user.avatar_url,
            specializations=[s.name for s in doctor.specializations],
        ),
        patient=PatientBrief(
            id=patient.id, full_name=patient.user.full_name, avatar_url=patient.user.avatar_url
        ),
        allowed_actions=allowed_actions(appointment, viewer, now or utcnow()),
    )


# --- Queries ---------------------------------------------------------------------


async def get_for_user(db: AsyncSession, appointment_id: int, user: User) -> Appointment:
    """Load an appointment the user is allowed to see. Anything else is a 404,
    so the existence of other people's appointments is not revealed."""
    appointment = await db.scalar(
        _with_parties(select(Appointment).where(Appointment.id == appointment_id))
    )
    if appointment is None or not _can_view(appointment, user):
        raise NotFoundError("Appointment not found")
    return appointment


def _can_view(appointment: Appointment, user: User) -> bool:
    if user.role == Role.ADMIN:
        return True
    if user.role == Role.DOCTOR:
        return appointment.doctor.user_id == user.id
    if user.role == Role.PATIENT:
        return appointment.patient.user_id == user.id
    return False


async def list_for_user(
    db: AsyncSession,
    user: User,
    page: PageParams,
    *,
    scope: Scope = "all",
    status: AppointmentStatus | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    doctor_id: int | None = None,
    patient_id: int | None = None,
    now: datetime | None = None,
) -> tuple[list[Appointment], int]:
    now = now or utcnow()
    query = select(Appointment)

    # Role scoping is applied first and cannot be widened by filters.
    if user.role == Role.PATIENT:
        query = query.join(Patient, Appointment.patient_id == Patient.id).where(
            Patient.user_id == user.id
        )
    elif user.role == Role.DOCTOR:
        query = query.join(Doctor, Appointment.doctor_id == Doctor.id).where(
            Doctor.user_id == user.id
        )
    elif user.role != Role.ADMIN:
        raise ForbiddenError()

    if doctor_id is not None:
        query = query.where(Appointment.doctor_id == doctor_id)
    if patient_id is not None:
        query = query.where(Appointment.patient_id == patient_id)
    if status is not None:
        query = query.where(Appointment.status == status)
    if date_from is not None:
        query = query.where(Appointment.starts_at >= clinic_day_bounds_utc(date_from)[0])
    if date_to is not None:
        query = query.where(Appointment.starts_at < clinic_day_bounds_utc(date_to)[1])

    active = Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES)
    ascending = scope == "upcoming" or (scope == "all" and (date_from or date_to))
    if scope == "upcoming":
        query = query.where(active, Appointment.ends_at > now)
    elif scope == "past":
        query = query.where(or_(Appointment.ends_at <= now, not_(active)))

    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = (
        (Appointment.starts_at.asc(), Appointment.id.asc())
        if ascending
        else (Appointment.starts_at.desc(), Appointment.id.desc())
    )
    rows = await db.scalars(
        _with_parties(query).order_by(*order).limit(page.page_size).offset(page.offset)
    )
    return list(rows), total


# --- Commands --------------------------------------------------------------------


async def book(
    db: AsyncSession,
    patient: Patient,
    patient_user: User,
    *,
    doctor_id: int,
    starts_at: datetime,
    reason: str | None,
    request: Request | None = None,
) -> Appointment:
    now = utcnow()
    doctor = await db.scalar(
        select(Doctor)
        .join(User, Doctor.user_id == User.id)
        .where(Doctor.id == doctor_id, User.is_active.is_(True), User.deleted_at.is_(None))
    )
    if doctor is None:
        raise NotFoundError("Doctor not found")

    slot = await slot_service.assert_bookable(db, doctor.id, starts_at, now)

    appointment = Appointment(
        doctor_id=doctor.id,
        patient_id=patient.id,
        starts_at=slot.starts_at,
        ends_at=slot.ends_at,
        status=AppointmentStatus.BOOKED,
        reason=reason,
        created_by_id=patient_user.id,
        updated_by_id=patient_user.id,
    )
    db.add(appointment)
    try:
        await db.flush()
    except OperationalError as exc:
        # InnoDB can resolve racing inserts on the same unique key with a
        # deadlock or lock-wait timeout instead of a duplicate-key error.
        if not is_lock_conflict(exc):
            raise
        await db.rollback()
        logger.info("Booking lock conflict for doctor %s", doctor_id)
        raise ConflictError("This slot is no longer available", code="slot_unavailable") from exc
    except IntegrityError as exc:
        # Lost a race with a concurrent booking: the unique index on
        # (doctor_id | patient_id, active_slot_starts_at) fired.
        await db.rollback()
        if "patient" in str(exc.orig).lower():
            raise ConflictError(
                "You already have an appointment at this time", code="patient_slot_conflict"
            ) from exc
        logger.info("Booking conflict for doctor %s at %s", doctor_id, slot.starts_at.isoformat())
        raise ConflictError("This slot is no longer available", code="slot_unavailable") from exc

    when = format_clinic_time(appointment.starts_at)
    notifier = Notifier(db)
    data = {"appointment_id": appointment.id}
    await notifier.add(
        patient_user.id,
        NotificationPayload(
            NotificationType.APPOINTMENT_BOOKED,
            "Appointment booked",
            f"Your appointment with Dr. {doctor.user.full_name} is booked for {when}.",
            data,
            dedupe_key=f"appointment:{appointment.id}:booked",
        ),
    )
    await notifier.add(
        doctor.user_id,
        NotificationPayload(
            NotificationType.APPOINTMENT_BOOKED,
            "New appointment",
            f"{patient_user.full_name} booked an appointment for {when}.",
            data,
            dedupe_key=f"appointment:{appointment.id}:booked",
        ),
    )
    audit_service.record(
        db,
        AuditAction.APPOINTMENT_BOOKED,
        actor_id=patient_user.id,
        entity_type="appointment",
        entity_id=appointment.id,
        details={"doctor_id": doctor.id, "starts_at": appointment.starts_at.isoformat()},
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
    return await get_for_user(db, appointment.id, patient_user)


async def perform_action(
    db: AsyncSession,
    appointment: Appointment,
    user: User,
    action: AppointmentAction,
    *,
    reason: str | None = None,
    doctor_notes: str | None = None,
    request: Request | None = None,
) -> Appointment:
    now = utcnow()
    check_action(appointment, user, action, now)
    previous = appointment.status
    appointment.status = ACTION_TARGET[action]
    appointment.updated_by_id = user.id

    if action == "confirm":
        appointment.confirmed_at = now
    elif action == "cancel":
        appointment.cancelled_at = now
        appointment.cancelled_by_id = user.id
        appointment.cancellation_reason = reason
    elif action == "complete":
        appointment.completed_at = now
        if doctor_notes:
            appointment.doctor_notes = doctor_notes

    notifier = Notifier(db)
    await _notify_transition(notifier, appointment, user, action)
    audit_service.record(
        db,
        AuditAction.APPOINTMENT_STATUS_CHANGED,
        actor_id=user.id,
        entity_type="appointment",
        entity_id=appointment.id,
        details={
            "from": previous.value,
            "to": appointment.status.value,
            "by_role": user.role.value,
        },
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("The appointment changed; please reload", code="conflict") from exc
    await notifier.dispatch()
    return await get_for_user(db, appointment.id, user)


async def _notify_transition(
    notifier: Notifier, appointment: Appointment, actor: User, action: AppointmentAction
) -> None:
    doctor_user, patient_user = appointment.doctor.user, appointment.patient.user
    when = format_clinic_time(appointment.starts_at)
    data = {"appointment_id": appointment.id}
    key = f"appointment:{appointment.id}:{action}"
    if action == "confirm":
        await notifier.add(
            patient_user.id,
            NotificationPayload(
                NotificationType.APPOINTMENT_CONFIRMED,
                "Appointment confirmed",
                f"Dr. {doctor_user.full_name} confirmed your appointment on {when}.",
                data,
                key,
            ),
        )
    elif action == "cancel":
        body = f"The appointment on {when} was cancelled."
        if appointment.cancellation_reason:
            body += f" Reason: {appointment.cancellation_reason}"
        for recipient in (doctor_user, patient_user):
            if recipient.id != actor.id:
                await notifier.add(
                    recipient.id,
                    NotificationPayload(
                        NotificationType.APPOINTMENT_CANCELLED,
                        "Appointment cancelled",
                        body,
                        data,
                        key,
                    ),
                )


async def cancel_future_for_doctor(
    db: AsyncSession, doctor: Doctor, actor: User, reason: str, notifier: Notifier
) -> int:
    """Cancel a doctor's upcoming active appointments (doctor deactivated or removed)."""
    now = utcnow()
    rows = await db.scalars(
        _with_parties(
            select(Appointment).where(
                Appointment.doctor_id == doctor.id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                Appointment.starts_at > now,
            )
        )
    )
    count = 0
    for appointment in rows:
        appointment.status = AppointmentStatus.CANCELLED
        appointment.cancelled_at = now
        appointment.cancelled_by_id = actor.id
        appointment.cancellation_reason = reason
        appointment.updated_by_id = actor.id
        await _notify_transition(notifier, appointment, actor, "cancel")
        count += 1
    return count


async def send_due_reminders(db: AsyncSession, now: datetime | None = None) -> int:
    """Notify both parties of appointments starting within REMINDER_LEAD_HOURS.
    Idempotent: guarded by reminder_sent_at and notification dedupe keys.
    Run periodically (cron/systemd timer): `python -m scripts.send_reminders`."""
    now = now or utcnow()
    horizon = now + timedelta(hours=settings.REMINDER_LEAD_HOURS)
    rows = list(
        await db.scalars(
            _with_parties(
                select(Appointment).where(
                    and_(
                        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                        Appointment.starts_at > now,
                        Appointment.starts_at <= horizon,
                        Appointment.reminder_sent_at.is_(None),
                    )
                )
            )
        )
    )
    notifier = Notifier(db)
    for appointment in rows:
        when = format_clinic_time(appointment.starts_at)
        data = {"appointment_id": appointment.id}
        key = f"appointment:{appointment.id}:reminder"
        await notifier.add(
            appointment.patient.user_id,
            NotificationPayload(
                NotificationType.APPOINTMENT_REMINDER,
                "Upcoming appointment",
                f"Reminder: you see Dr. {appointment.doctor.user.full_name} on {when}.",
                data,
                key,
            ),
        )
        await notifier.add(
            appointment.doctor.user_id,
            NotificationPayload(
                NotificationType.APPOINTMENT_REMINDER,
                "Upcoming appointment",
                f"Reminder: {appointment.patient.user.full_name} on {when}.",
                data,
                key,
            ),
        )
        appointment.reminder_sent_at = now
    await db.commit()
    await notifier.dispatch()
    return len(rows)


async def doctor_patients(
    db: AsyncSession, doctor: Doctor, page: PageParams, search: str | None = None
) -> tuple[list[tuple[Patient, datetime, int]], int]:
    """Patients who have (had) appointments with this doctor, with their latest
    appointment time and appointment count."""
    stats = (
        select(
            Appointment.patient_id,
            func.max(Appointment.starts_at).label("last_at"),
            func.count(Appointment.id).label("visits"),
        )
        .where(Appointment.doctor_id == doctor.id)
        .group_by(Appointment.patient_id)
        .subquery()
    )
    query = (
        select(Patient, stats.c.last_at, stats.c.visits)
        .join(stats, stats.c.patient_id == Patient.id)
        .join(User, Patient.user_id == User.id)
    )
    if search:
        term = f"%{escape_like(search.strip().lower())}%"
        query = query.where(
            or_(
                func.lower(User.first_name).like(term, escape=LIKE_ESCAPE),
                func.lower(User.last_name).like(term, escape=LIKE_ESCAPE),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.execute(
        query.order_by(stats.c.last_at.desc()).limit(page.page_size).offset(page.offset)
    )
    return [(row[0], row[1], row[2]) for row in rows], total


async def doctor_has_patient(db: AsyncSession, doctor_id: int, patient_id: int) -> bool:
    return bool(
        await db.scalar(
            select(Appointment.id)
            .where(Appointment.doctor_id == doctor_id, Appointment.patient_id == patient_id)
            .limit(1)
        )
    )
