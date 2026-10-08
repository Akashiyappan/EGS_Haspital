from datetime import date, datetime, timedelta
from itertools import combinations

from fastapi import Request
from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, NotFoundError
from app.core.timeutils import clinic_today, utcnow
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    Doctor,
    DoctorSchedule,
    DoctorTimeOff,
    NotificationType,
    User,
)
from app.schemas.doctor import ScheduleRuleIn, TimeOffCreate
from app.services import audit_service, slot_service
from app.services.audit_service import AuditAction
from app.services.notification_service import NotificationPayload, Notifier

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _date_ranges_overlap(a: ScheduleRuleIn, b: ScheduleRuleIn) -> bool:
    a_from, a_until = a.effective_from or date.min, a.effective_until or date.max
    b_from, b_until = b.effective_from or date.min, b.effective_until or date.max
    return a_from <= b_until and b_from <= a_until


def validate_rules(rules: list[ScheduleRuleIn]) -> None:
    for a, b in combinations(rules, 2):
        if (
            a.weekday == b.weekday
            and a.start_time < b.end_time
            and b.start_time < a.end_time
            and _date_ranges_overlap(a, b)
        ):
            raise AppError(
                f"Overlapping working periods on {WEEKDAYS[a.weekday]}: "
                f"{a.start_time:%H:%M}-{a.end_time:%H:%M} and {b.start_time:%H:%M}-{b.end_time:%H:%M}",
                code="schedule_overlap",
            )


async def get_rules(db: AsyncSession, doctor_id: int) -> list[DoctorSchedule]:
    return list(
        await db.scalars(
            select(DoctorSchedule)
            .where(DoctorSchedule.doctor_id == doctor_id)
            .order_by(DoctorSchedule.weekday, DoctorSchedule.start_time)
        )
    )


async def conflicting_appointments(db: AsyncSession, doctor_id: int) -> list[int]:
    """Upcoming active appointments whose time no longer matches the schedule
    (including time off). They are kept, but surfaced to the admin."""
    now = utcnow()
    upcoming = list(
        await db.execute(
            select(Appointment.id, Appointment.starts_at).where(
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
                Appointment.starts_at > now,
            )
        )
    )
    if not upcoming:
        return []
    tz = settings.clinic_tz
    days = [row[1].astimezone(tz).date() for row in upcoming]
    valid = await slot_service.valid_slot_starts(db, doctor_id, min(days), max(days))
    return sorted(row[0] for row in upcoming if row[1] not in valid)


async def _notify_doctor(db: AsyncSession, doctor: Doctor, body: str) -> Notifier:
    notifier = Notifier(db)
    await notifier.add(
        doctor.user_id,
        NotificationPayload(NotificationType.SCHEDULE_CHANGED, "Schedule updated", body),
    )
    return notifier


async def replace_rules(
    db: AsyncSession,
    doctor: Doctor,
    rules: list[ScheduleRuleIn],
    actor: User,
    request: Request | None,
) -> tuple[list[DoctorSchedule], list[int]]:
    validate_rules(rules)
    await db.execute(delete(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor.id))
    for rule in rules:
        db.add(
            DoctorSchedule(
                doctor_id=doctor.id,
                weekday=rule.weekday,
                start_time=rule.start_time,
                end_time=rule.end_time,
                slot_minutes=rule.slot_minutes or settings.APPOINTMENT_DURATION_MINUTES,
                effective_from=rule.effective_from,
                effective_until=rule.effective_until,
                created_by_id=actor.id,
            )
        )
    await db.flush()
    conflicts = await conflicting_appointments(db, doctor.id)
    notifier = await _notify_doctor(db, doctor, "Your weekly working schedule was updated.")
    audit_service.record(
        db,
        AuditAction.SCHEDULE_CHANGED,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        details={"rules": len(rules), "conflicting_appointments": len(conflicts)},
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
    return await get_rules(db, doctor.id), conflicts


async def list_time_off(
    db: AsyncSession, doctor_id: int | None, *, include_clinic_wide: bool = True
) -> list[DoctorTimeOff]:
    """Current and future time off for a doctor (and clinic-wide entries)."""
    since = utcnow() - timedelta(days=1)
    query = select(DoctorTimeOff).where(DoctorTimeOff.ends_at > since)
    if doctor_id is None:
        query = query.where(DoctorTimeOff.doctor_id.is_(None))
    elif include_clinic_wide:
        query = query.where(
            or_(DoctorTimeOff.doctor_id == doctor_id, DoctorTimeOff.doctor_id.is_(None))
        )
    else:
        query = query.where(DoctorTimeOff.doctor_id == doctor_id)
    return list(await db.scalars(query.order_by(DoctorTimeOff.starts_at)))


async def add_time_off(
    db: AsyncSession,
    doctor: Doctor | None,
    data: TimeOffCreate,
    actor: User,
    request: Request | None,
) -> tuple[DoctorTimeOff, list[int]]:
    if data.ends_at <= utcnow():
        raise AppError("Time off must end in the future", code="time_off_in_past")
    entry = DoctorTimeOff(
        doctor_id=doctor.id if doctor else None,
        kind=data.kind,
        starts_at=data.starts_at,
        ends_at=data.ends_at,
        reason=data.reason,
        created_by_id=actor.id,
    )
    db.add(entry)
    await db.flush()

    overlap = select(Appointment.id).where(
        Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
        Appointment.starts_at < entry.ends_at,
        Appointment.ends_at > entry.starts_at,
    )
    if doctor is not None:
        overlap = overlap.where(Appointment.doctor_id == doctor.id)
    conflicts = sorted(await db.scalars(overlap))

    notifier = Notifier(db)
    if doctor is not None:
        notifier = await _notify_doctor(
            db, doctor, f"Time off was added to your calendar ({entry.kind.lower()})."
        )
    audit_service.record(
        db,
        AuditAction.TIME_OFF_ADDED,
        actor_id=actor.id,
        entity_type="time_off",
        entity_id=entry.id,
        details={
            "doctor_id": entry.doctor_id,
            "kind": entry.kind.value,
            "conflicting_appointments": len(conflicts),
        },
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
    return entry, conflicts


async def remove_time_off(
    db: AsyncSession, time_off_id: int, actor: User, request: Request | None
) -> None:
    entry = await db.get(DoctorTimeOff, time_off_id)
    if entry is None:
        raise NotFoundError("Time off entry not found")
    audit_service.record(
        db,
        AuditAction.TIME_OFF_REMOVED,
        actor_id=actor.id,
        entity_type="time_off",
        entity_id=entry.id,
        details={"doctor_id": entry.doctor_id},
        request=request,
    )
    await db.delete(entry)
    await db.commit()


def availability_range(start: date | None, days: int, now: datetime) -> tuple[date, date]:
    first = max(start or clinic_today(now), clinic_today(now))
    return first, first + timedelta(days=days - 1)
