"""Timezone strategy: every instant is stored and exchanged in UTC. Doctor
schedules are wall-clock times in the clinic timezone, converted to UTC only
when concrete slots are generated (so DST shifts are handled per date)."""

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings


def utcnow() -> datetime:
    return datetime.now(UTC)


def clinic_today(now: datetime | None = None) -> date:
    return (now or utcnow()).astimezone(settings.clinic_tz).date()


def local_to_utc(day: date, wall_time: time, tz: ZoneInfo) -> datetime | None:
    """Convert a clinic wall-clock time to UTC.

    Returns None for wall-clock times that do not exist on that date (the gap
    when clocks spring forward). Ambiguous times (clocks falling back) resolve
    to the first occurrence.
    """
    local = datetime.combine(day, wall_time, tzinfo=tz).replace(fold=0)
    as_utc = local.astimezone(UTC)
    if as_utc.astimezone(tz).replace(tzinfo=None) != local.replace(tzinfo=None):
        return None
    return as_utc


def clinic_day_bounds_utc(day: date, tz: ZoneInfo | None = None) -> tuple[datetime, datetime]:
    zone = tz or settings.clinic_tz
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return start, end


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Datetime must include a timezone offset")
    return value.astimezone(UTC)
