import asyncio
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.timeutils import utcnow
from app.models import Appointment, AppointmentStatus, Notification
from app.services import slot_service
from app.services.appointment_service import send_due_reminders
from tests.helpers import (
    API,
    booking_day,
    iso,
    login,
    make_admin,
    make_appointment,
    make_doctor,
    make_patient,
    slot_start,
)


async def book(client: AsyncClient, headers: dict, doctor_id: int, starts_at, reason=None):  # type: ignore[no-untyped-def]
    return await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor_id, "starts_at": iso(starts_at), "reason": reason},
        headers=headers,
    )


@pytest.fixture
async def setup(client: AsyncClient, session_factory):  # type: ignore[no-untyped-def]
    doctor_user, doctor = await make_doctor(session_factory)
    patient_user, patient_id = await make_patient(session_factory)
    return {
        "doctor": doctor,
        "doctor_user": doctor_user,
        "patient_user": patient_user,
        "patient_id": patient_id,
        "patient": await login(client, "patient@example.com"),
        "doctor_h": await login(client, "doctor@example.com", portal="staff"),
    }


async def test_book_appointment(client: AsyncClient, session_factory, setup) -> None:
    res = await book(client, setup["patient"], setup["doctor"].id, slot_start(), "Chest discomfort")
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "BOOKED"
    assert body["doctor"]["specializations"] == ["Cardiology"]
    assert body["allowed_actions"] == ["cancel"]
    assert body["doctor_notes"] is None

    slots = await client.get(
        f"{API}/doctors/{setup['doctor'].id}/slots",
        params={"date": booking_day().isoformat()},
        headers=setup["patient"],
    )
    taken = [s for s in slots.json()["slots"] if s["starts_at"].startswith(iso(slot_start())[:16])]
    assert taken and taken[0]["available"] is False

    async with session_factory() as db:
        recipients = set(await db.scalars(select(Notification.user_id)))
    assert recipients == {setup["patient_user"].id, setup["doctor_user"].id}


async def test_same_slot_twice_conflicts(client: AsyncClient, session_factory, setup) -> None:
    await make_patient(session_factory, "second@example.com")
    second = await login(client, "second@example.com")
    assert (
        await book(client, setup["patient"], setup["doctor"].id, slot_start())
    ).status_code == 201
    res = await book(client, second, setup["doctor"].id, slot_start())
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "slot_unavailable"


async def test_concurrent_booking_only_one_succeeds(
    client: AsyncClient, session_factory, setup
) -> None:
    """Critical: N patients racing for one slot -> exactly one 201, the rest 409."""
    headers = [setup["patient"]]
    for i in range(4):
        await make_patient(session_factory, f"racer{i}@example.com")
        headers.append(await login(client, f"racer{i}@example.com"))

    results = await asyncio.gather(
        *(book(client, h, setup["doctor"].id, slot_start()) for h in headers)
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 409, 409, 409, 409]
    async with session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(Appointment))
    assert count == 1


async def test_database_constraint_blocks_double_booking_without_precheck(
    client: AsyncClient, session_factory, setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if the application-level availability check is bypassed (two requests
    pass it simultaneously), the database unique index must reject the second insert."""

    async def always_free(db, doctor_id, starts_at, now):  # type: ignore[no-untyped-def]
        return slot_service.Slot(
            starts_at=starts_at, ends_at=starts_at + timedelta(minutes=30), available=True
        )

    monkeypatch.setattr(slot_service, "assert_bookable", always_free)
    await make_patient(session_factory, "other@example.com")
    other = await login(client, "other@example.com")

    first, second = await asyncio.gather(
        book(client, setup["patient"], setup["doctor"].id, slot_start()),
        book(client, other, setup["doctor"].id, slot_start()),
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    loser = first if first.status_code == 409 else second
    assert loser.json()["error"]["code"] == "slot_unavailable"


async def test_patient_cannot_be_in_two_places(client: AsyncClient, session_factory, setup) -> None:
    await make_doctor(session_factory, "doc2@example.com", specialization="Neurology")
    async with session_factory() as db:
        from app.models import Doctor

        doctor2_id = await db.scalar(select(Doctor.id).order_by(Doctor.id.desc()))
    assert (
        await book(client, setup["patient"], setup["doctor"].id, slot_start())
    ).status_code == 201
    res = await book(client, setup["patient"], doctor2_id, slot_start())
    assert res.status_code == 409


async def test_invalid_slots_rejected(client: AsyncClient, setup) -> None:
    doctor_id = setup["doctor"].id
    off_grid = await book(client, setup["patient"], doctor_id, slot_start(minute=15))
    outside = await book(client, setup["patient"], doctor_id, slot_start(hour=12))
    past = await book(client, setup["patient"], doctor_id, slot_start(days_ahead=-1))
    too_far = await book(client, setup["patient"], doctor_id, slot_start(days_ahead=400))
    for res in (off_grid, outside, past, too_far):
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "invalid_slot"
    naive = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor_id, "starts_at": "2030-01-01T08:00:00"},
        headers=setup["patient"],
    )
    assert naive.status_code == 422
    unknown = await book(client, setup["patient"], 9999, slot_start())
    assert unknown.status_code == 404


async def test_cancel_frees_the_slot(client: AsyncClient, session_factory, setup) -> None:
    booked = await book(client, setup["patient"], setup["doctor"].id, slot_start())
    cancel = await client.post(
        f"{API}/appointments/{booked.json()['id']}/cancel",
        json={"reason": "Feeling better"},
        headers=setup["patient"],
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"
    assert cancel.json()["allowed_actions"] == []
    again = await client.post(
        f"{API}/appointments/{booked.json()['id']}/cancel", json={}, headers=setup["patient"]
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "invalid_transition"
    rebook = await book(client, setup["patient"], setup["doctor"].id, slot_start())
    assert rebook.status_code == 201


async def test_cancellation_cutoff(client: AsyncClient, session_factory, setup) -> None:
    soon = utcnow().replace(microsecond=0) + timedelta(minutes=30)
    appointment_id = await make_appointment(
        session_factory, setup["doctor"].id, setup["patient_id"], soon
    )
    res = await client.post(
        f"{API}/appointments/{appointment_id}/cancel", json={}, headers=setup["patient"]
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "cancellation_window_closed"
    by_doctor = await client.post(
        f"{API}/appointments/{appointment_id}/cancel", json={}, headers=setup["doctor_h"]
    )
    assert by_doctor.status_code == 200


async def test_state_machine(client: AsyncClient, session_factory, setup) -> None:
    started = utcnow().replace(microsecond=0) - timedelta(minutes=10)
    appointment_id = await make_appointment(
        session_factory, setup["doctor"].id, setup["patient_id"], started
    )
    url = f"{API}/appointments/{appointment_id}"

    # Patients can only cancel.
    assert (await client.post(f"{url}/confirm", headers=setup["patient"])).status_code == 403
    # BOOKED cannot jump straight to COMPLETED.
    skip = await client.post(f"{url}/complete", json={}, headers=setup["doctor_h"])
    assert skip.status_code == 409 and skip.json()["error"]["code"] == "invalid_transition"

    confirm = await client.post(f"{url}/confirm", headers=setup["doctor_h"])
    assert confirm.status_code == 200 and confirm.json()["status"] == "CONFIRMED"
    complete = await client.post(
        f"{url}/complete", json={"doctor_notes": "Advised rest"}, headers=setup["doctor_h"]
    )
    assert complete.status_code == 200
    assert complete.json()["status"] == "COMPLETED"
    assert complete.json()["doctor_notes"] == "Advised rest"

    patient_view = await client.get(url, headers=setup["patient"])
    assert patient_view.json()["doctor_notes"] is None  # clinical notes are staff-only
    terminal = await client.post(f"{url}/no-show", headers=setup["doctor_h"])
    assert terminal.status_code == 409


async def test_cannot_complete_before_start(client: AsyncClient, session_factory, setup) -> None:
    appointment_id = await make_appointment(
        session_factory,
        setup["doctor"].id,
        setup["patient_id"],
        slot_start(),
        AppointmentStatus.CONFIRMED,
    )
    res = await client.post(
        f"{API}/appointments/{appointment_id}/complete", json={}, headers=setup["doctor_h"]
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "appointment_not_started"


async def test_access_is_scoped(client: AsyncClient, session_factory, setup) -> None:
    booked = await book(client, setup["patient"], setup["doctor"].id, slot_start())
    appointment_id = booked.json()["id"]

    await make_patient(session_factory, "nosy@example.com")
    nosy = await login(client, "nosy@example.com")
    await make_doctor(session_factory, "otherdoc@example.com")
    other_doctor = await login(client, "otherdoc@example.com", portal="staff")
    await make_admin(session_factory)
    admin = await login(client, "admin@example.com", portal="staff")

    for headers in (nosy, other_doctor):
        assert (
            await client.get(f"{API}/appointments/{appointment_id}", headers=headers)
        ).status_code == 404
        cancel = await client.post(
            f"{API}/appointments/{appointment_id}/cancel", json={}, headers=headers
        )
        assert cancel.status_code == 404
        listing = await client.get(f"{API}/appointments", headers=headers)
        assert listing.json()["total"] == 0

    # Filters cannot widen a non-admin's scope.
    widened = await client.get(
        f"{API}/appointments", params={"patient_id": setup["patient_id"]}, headers=other_doctor
    )
    assert widened.json()["total"] == 0

    assert (
        await client.get(f"{API}/appointments/{appointment_id}", headers=admin)
    ).status_code == 200
    assert (await client.get(f"{API}/appointments", headers=admin)).json()["total"] == 1


async def test_upcoming_and_past_lists(client: AsyncClient, session_factory, setup) -> None:
    await book(client, setup["patient"], setup["doctor"].id, slot_start())
    await make_appointment(
        session_factory,
        setup["doctor"].id,
        setup["patient_id"],
        utcnow().replace(microsecond=0) - timedelta(days=3),
        AppointmentStatus.COMPLETED,
    )
    upcoming = await client.get(
        f"{API}/appointments", params={"scope": "upcoming"}, headers=setup["patient"]
    )
    past = await client.get(
        f"{API}/appointments", params={"scope": "past"}, headers=setup["patient"]
    )
    assert [a["status"] for a in upcoming.json()["items"]] == ["BOOKED"]
    assert [a["status"] for a in past.json()["items"]] == ["COMPLETED"]

    patients = await client.get(f"{API}/doctor/patients", headers=setup["doctor_h"])
    assert patients.json()["total"] == 1
    assert patients.json()["items"][0]["appointment_count"] == 2
    detail = await client.get(
        f"{API}/doctor/patients/{setup['patient_id']}", headers=setup["doctor_h"]
    )
    assert detail.status_code == 200 and detail.json()["email"] == "patient@example.com"


async def test_doctor_cannot_view_unrelated_patient(
    client: AsyncClient, session_factory, setup
) -> None:
    _, stranger_id = await make_patient(session_factory, "stranger@example.com")
    res = await client.get(f"{API}/doctor/patients/{stranger_id}", headers=setup["doctor_h"])
    assert res.status_code == 404


async def test_reminders_are_sent_once(client: AsyncClient, session_factory, setup) -> None:
    soon = utcnow().replace(microsecond=0) + timedelta(hours=3)
    await make_appointment(session_factory, setup["doctor"].id, setup["patient_id"], soon)
    async with session_factory() as db:
        assert await send_due_reminders(db) == 1
    async with session_factory() as db:
        assert await send_due_reminders(db) == 0
        count = await db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.type == "APPOINTMENT_REMINDER")
        )
    assert count == 2  # patient + doctor, no duplicates
