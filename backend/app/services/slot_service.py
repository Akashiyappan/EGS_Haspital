"""Appointment slot generation. The backend is the single source of truth for
what can be booked; the UI only renders what this module returns.

Slots are produced from the doctor's recurring schedule rules (clinic-local
wall-clock), minus time off (doctor or clinic-wide), with existing active
appointments marking slots unavailable. Wall-clock times are converted to UTC
per date, so DST transitions are handled: non-existent local times are skipped
and ambiguous ones resolve to their first occurrence.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ConflictError
from app.core.timeutils import clinic_day_bounds_utc, clinic_today, local_to_utc
from app.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    DoctorSchedule,
    DoctorTimeOff,
)

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class Slot:
    starts_at: datetime
    ends_at: datetime
    available: bool


def _rule_applies(rule: DoctorSchedule, day: date) -> bool:
    return (
        rule.weekday == day.weekday()
        and (rule.effective_from is None or rule.effective_from <= day)
        and (rule.effective_until is None or day <= rule.effective_until)
    )


def _overlaps(start: datetime, end: datetime, intervals: Iterable[Interval]) -> bool:
    return any(other_start < end and start < other_end for other_start, other_end in intervals)


def build_day_slots(
    day: date,
    rules: Sequence[DoctorSchedule],
    *,
    tz: ZoneInfo,
    blocked: Sequence[Interval] = (),
    booked: Sequence[Interval] = (),
    earliest_bookable: datetime | None = None,
) -> list[Slot]:
    """Pure slot generation for one clinic-local day.

    Slots overlapping `blocked` (time off) are omitted entirely; slots
    overlapping `booked` or starting before `earliest_bookable` are returned
    with available=False.
    """
    slots: dict[datetime, Slot] = {}
    for rule in rules:
        if not _rule_applies(rule, day):
            continue
        step = timedelta(minutes=rule.slot_minutes)
        cursor = datetime.combine(day, rule.start_time)
        period_end = datetime.combine(day, rule.end_time)
        while cursor + step <= period_end:
            start = local_to_utc(day, cursor.time(), tz)
            cursor += step
            if start is None or start in slots:
                continue
            end = start + step
            if _overlaps(start, end, blocked):
                continue
            available = not _overlaps(start, end, booked) and (
                earliest_bookable is None or start >= earliest_bookable
            )
            slots[start] = Slot(starts_at=start, ends_at=end, available=available)
    return sorted(slots.values(), key=lambda slot: slot.starts_at)


@dataclass
class _DoctorCalendar:
    rules: list[DoctorSchedule]
    blocked: list[Interval]
    booked: list[Interval]


async def _load_calendar(
    db: AsyncSession, doctor_id: int, range_start: datetime, range_end: datetime
) -> _DoctorCalendar:
    rules = list(
        await db.scalars(select(DoctorSchedule).where(DoctorSchedule.doctor_id == doctor_id))
    )
    time_off = await db.execute(
        select(DoctorTimeOff.starts_at, DoctorTimeOff.ends_at).where(
            or_(DoctorTimeOff.doctor_id == doctor_id, DoctorTimeOff.doctor_id.is_(None)),
            DoctorTimeOff.starts_at < range_end,
            DoctorTimeOff.ends_at > range_start,
        )
    )
    booked = await db.execute(
        select(Appointment.starts_at, Appointment.ends_at).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status.in_(ACTIVE_APPOINTMENT_STATUSES),
            Appointment.starts_at < range_end,
            Appointment.ends_at > range_start,
        )
    )
    return _DoctorCalendar(
        rules=rules,
        blocked=[(row[0], row[1]) for row in time_off],
        booked=[(row[0], row[1]) for row in booked],
    )


def bookable_days(first_day: date, last_day: date, now: datetime) -> list[date]:
    """Days inside the booking window [today, today + BOOKING_WINDOW_DAYS]."""
    today = clinic_today(now)
    window_end = today + timedelta(days=settings.BOOKING_WINDOW_DAYS)
    start, end = max(first_day, today), min(last_day, window_end)
    return (
        [start + timedelta(days=i) for i in range((end - start).days + 1)] if start <= end else []
    )


async def slots_for_range(
    db: AsyncSession, doctor_id: int, first_day: date, last_day: date, now: datetime
) -> dict[date, list[Slot]]:
    days = bookable_days(first_day, last_day, now)
    if not days:
        return {}
    tz = settings.clinic_tz
    range_start, _ = clinic_day_bounds_utc(days[0], tz)
    _, range_end = clinic_day_bounds_utc(days[-1], tz)
    calendar = await _load_calendar(db, doctor_id, range_start, range_end)
    earliest = now + timedelta(minutes=settings.BOOKING_MIN_LEAD_MINUTES)
    return {
        day: build_day_slots(
            day,
            calendar.rules,
            tz=tz,
            blocked=calendar.blocked,
            booked=calendar.booked,
            earliest_bookable=earliest,
        )
        for day in days
    }


async def assert_bookable(
    db: AsyncSession, doctor_id: int, starts_at: datetime, now: datetime
) -> Slot:
    """Validate that `starts_at` is exactly one of the doctor's free slots.

    This is a fast, friendly pre-check; the unique index on
    appointments is what actually guarantees no double booking under
    concurrency.
    """
    start = starts_at.astimezone(UTC)
    day = start.astimezone(settings.clinic_tz).date()
    slots = (await slots_for_range(db, doctor_id, day, day, now)).get(day, [])
    match = next((slot for slot in slots if slot.starts_at == start), None)
    if match is None:
        raise AppError(
            "The selected time is not an available slot for this doctor", code="invalid_slot"
        )
    if not match.available:
        raise ConflictError("This slot is no longer available", code="slot_unavailable")
    return match


async def valid_slot_starts(
    db: AsyncSession, doctor_id: int, first_day: date, last_day: date
) -> set[datetime]:
    """Every slot start the schedule allows (ignoring bookings and lead time).
    Used to find booked appointments that no longer fit a changed schedule."""
    tz = settings.clinic_tz
    range_start, _ = clinic_day_bounds_utc(first_day, tz)
    _, range_end = clinic_day_bounds_utc(last_day, tz)
    calendar = await _load_calendar(db, doctor_id, range_start, range_end)
    starts: set[datetime] = set()
    day = first_day
    while day <= last_day:
        starts.update(
            slot.starts_at
            for slot in build_day_slots(day, calendar.rules, tz=tz, blocked=calendar.blocked)
        )
        day += timedelta(days=1)
    return starts
