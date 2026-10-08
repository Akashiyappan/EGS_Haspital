from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from httpx import AsyncClient

from app.models import DoctorSchedule
from app.services.slot_service import build_day_slots
from tests.helpers import (
    API,
    booking_day,
    iso,
    login,
    make_admin,
    make_doctor,
    make_patient,
    slot_start,
)

IST = ZoneInfo("Asia/Kolkata")
MONDAY = date(2030, 1, 7)


def rule(weekday: int, start: time, end: time, **kw) -> DoctorSchedule:
    return DoctorSchedule(weekday=weekday, start_time=start, end_time=end, slot_minutes=30, **kw)


# --- Pure slot generation --------------------------------------------------------


def test_two_hour_period_gives_four_thirty_minute_slots() -> None:
    slots = build_day_slots(MONDAY, [rule(0, time(8), time(10))], tz=IST)
    local = [s.starts_at.astimezone(IST).strftime("%H:%M") for s in slots]
    assert local == ["08:00", "08:30", "09:00", "09:30"]
    assert all(s.ends_at - s.starts_at == timedelta(minutes=30) for s in slots)
    assert slots[0].starts_at == datetime(2030, 1, 7, 2, 30, tzinfo=UTC)  # 08:00 IST


def test_no_slots_outside_working_hours_or_on_other_days() -> None:
    rules = [rule(0, time(8), time(10))]
    assert build_day_slots(MONDAY + timedelta(days=1), rules, tz=IST) == []
    partial = build_day_slots(MONDAY, [rule(0, time(8), time(9, 45))], tz=IST)
    assert len(partial) == 3  # a trailing 15 minutes is not a slot


def test_multiple_shifts_and_effective_dates() -> None:
    rules = [
        rule(0, time(8), time(10)),
        rule(0, time(14), time(15)),
        rule(0, time(18), time(19), effective_from=MONDAY + timedelta(days=7)),
    ]
    assert len(build_day_slots(MONDAY, rules, tz=IST)) == 6
    assert len(build_day_slots(MONDAY + timedelta(days=7), rules, tz=IST)) == 8


def test_time_off_removes_and_bookings_disable_slots() -> None:
    rules = [rule(0, time(8), time(10))]
    first = datetime(2030, 1, 7, 2, 30, tzinfo=UTC)
    slots = build_day_slots(
        MONDAY,
        rules,
        tz=IST,
        blocked=[(first, first + timedelta(minutes=30))],
        booked=[(first + timedelta(minutes=30), first + timedelta(minutes=60))],
    )
    assert len(slots) == 3
    assert [s.available for s in slots] == [False, True, True]


def test_dst_spring_forward_skips_nonexistent_times() -> None:
    new_york = ZoneInfo("America/New_York")
    dst_day = date(2030, 3, 10)  # clocks jump 02:00 -> 03:00
    slots = build_day_slots(dst_day, [rule(dst_day.weekday(), time(1), time(4))], tz=new_york)
    local = [s.starts_at.astimezone(new_york).strftime("%H:%M") for s in slots]
    assert local == ["01:00", "01:30", "03:00", "03:30"]
    assert len({s.starts_at for s in slots}) == len(slots)


# --- API -------------------------------------------------------------------------


async def _admin(client: AsyncClient, session_factory) -> dict[str, str]:
    await make_admin(session_factory)
    return await login(client, "admin@example.com", portal="staff")


async def test_replace_schedule_and_slots(client: AsyncClient, session_factory) -> None:
    headers = await _admin(client, session_factory)
    _, doctor = await make_doctor(session_factory, with_schedule=False)
    day = booking_day()
    schedule = await client.put(
        f"{API}/admin/doctors/{doctor.id}/schedule",
        json={"rules": [{"weekday": day.weekday(), "start_time": "08:00", "end_time": "10:00"}]},
        headers=headers,
    )
    assert schedule.status_code == 200, schedule.text
    assert schedule.json()["rules"][0]["slot_minutes"] == 30

    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    slots = await client.get(
        f"{API}/doctors/{doctor.id}/slots", params={"date": day.isoformat()}, headers=patient
    )
    assert slots.status_code == 200
    assert len(slots.json()["slots"]) == 4
    assert all(s["available"] for s in slots.json()["slots"])

    availability = await client.get(
        f"{API}/doctors/{doctor.id}/availability", params={"days": 7}, headers=patient
    )
    by_date = {d["date"]: d["available_slots"] for d in availability.json()["days"]}
    assert by_date[day.isoformat()] == 4


async def test_overlapping_schedule_rejected(client: AsyncClient, session_factory) -> None:
    headers = await _admin(client, session_factory)
    _, doctor = await make_doctor(session_factory, with_schedule=False)
    res = await client.put(
        f"{API}/admin/doctors/{doctor.id}/schedule",
        json={
            "rules": [
                {"weekday": 0, "start_time": "08:00", "end_time": "10:00"},
                {"weekday": 0, "start_time": "09:30", "end_time": "11:00"},
            ]
        },
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "schedule_overlap"

    invalid = await client.put(
        f"{API}/admin/doctors/{doctor.id}/schedule",
        json={"rules": [{"weekday": 0, "start_time": "10:00", "end_time": "09:00"}]},
        headers=headers,
    )
    assert invalid.status_code == 422


async def test_time_off_hides_slots_and_reports_conflicts(
    client: AsyncClient, session_factory
) -> None:
    headers = await _admin(client, session_factory)
    _, doctor = await make_doctor(session_factory)
    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    booked = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient,
    )
    assert booked.status_code == 201

    start = slot_start()
    leave = await client.post(
        f"{API}/admin/doctors/{doctor.id}/time-off",
        json={"kind": "LEAVE", "starts_at": iso(start), "ends_at": iso(start + timedelta(hours=2))},
        headers=headers,
    )
    assert leave.status_code == 201
    assert leave.json()["conflicting_appointment_ids"] == [booked.json()["id"]]

    slots = await client.get(
        f"{API}/doctors/{doctor.id}/slots",
        params={"date": booking_day().isoformat()},
        headers=patient,
    )
    assert slots.json()["slots"] == []

    removed = await client.delete(f"{API}/admin/time-off/{leave.json()['id']}", headers=headers)
    assert removed.status_code == 204


async def test_schedule_change_reports_conflicting_appointments(
    client: AsyncClient, session_factory
) -> None:
    headers = await _admin(client, session_factory)
    _, doctor = await make_doctor(session_factory)
    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    booked = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient,
    )
    res = await client.put(
        f"{API}/admin/doctors/{doctor.id}/schedule",
        json={"rules": [{"weekday": 0, "start_time": "14:00", "end_time": "15:00"}]},
        headers=headers,
    )
    assert res.status_code == 200
    # The 08:00 booking no longer fits a Monday 14:00-15:00 schedule on any weekday.
    assert res.json()["conflicting_appointment_ids"] == [booked.json()["id"]]


async def test_clinic_holiday_blocks_all_doctors(client: AsyncClient, session_factory) -> None:
    headers = await _admin(client, session_factory)
    _, doctor = await make_doctor(session_factory)
    start = slot_start(hour=0)
    holiday = await client.post(
        f"{API}/admin/time-off",
        json={
            "kind": "HOLIDAY",
            "starts_at": iso(start),
            "ends_at": iso(start + timedelta(days=1)),
        },
        headers=headers,
    )
    assert holiday.status_code == 201
    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    slots = await client.get(
        f"{API}/doctors/{doctor.id}/slots",
        params={"date": booking_day().isoformat()},
        headers=patient,
    )
    assert slots.json()["slots"] == []


async def test_doctor_sees_own_schedule(client: AsyncClient, session_factory) -> None:
    await make_doctor(session_factory)
    headers = await login(client, "doctor@example.com", portal="staff")
    res = await client.get(f"{API}/doctor/schedule", headers=headers)
    assert res.status_code == 200
    assert len(res.json()["rules"]) == 7
