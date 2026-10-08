from httpx import AsyncClient
from sqlalchemy import select

from app.models import AppointmentStatus, AuditLog, Notification
from tests.helpers import (
    API,
    PASSWORD,
    iso,
    login,
    make_admin,
    make_doctor,
    make_patient,
    make_specialization,
    slot_start,
)


async def admin_headers(client: AsyncClient, session_factory) -> dict[str, str]:
    await make_admin(session_factory)
    return await login(client, "admin@example.com", portal="staff")


def doctor_payload(spec_ids: list[int], **overrides) -> dict:
    return {
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": "grace@example.com",
        "temporary_password": "TempPass1",
        "phone": "+91 98765 43210",
        "specialization_ids": spec_ids,
        "qualification": "MBBS, MD",
        "experience_years": 10,
        "bio": "Cardiologist.",
        **overrides,
    }


async def test_create_doctor_and_first_login(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    spec = await make_specialization(session_factory, "Cardiology")

    res = await client.post(f"{API}/admin/doctors", json=doctor_payload([spec.id]), headers=headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["specializations"][0]["name"] == "Cardiology"
    assert body["must_change_password"] is True
    assert "TempPass1" not in res.text and "password" not in body

    login_res = await client.post(
        f"{API}/auth/login",
        json={"email": "grace@example.com", "password": "TempPass1", "portal": "staff"},
    )
    assert login_res.status_code == 200
    assert login_res.json()["role"] == "DOCTOR"
    assert login_res.json()["must_change_password"] is True

    async with session_factory() as db:
        actions = list(await db.scalars(select(AuditLog.action)))
    assert "doctor.created" in actions


async def test_create_doctor_validation(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    spec = await make_specialization(session_factory)
    bad_spec = await client.post(
        f"{API}/admin/doctors", json=doctor_payload([9999]), headers=headers
    )
    assert bad_spec.status_code == 400
    assert bad_spec.json()["error"]["code"] == "invalid_specialization"

    no_spec = await client.post(f"{API}/admin/doctors", json=doctor_payload([]), headers=headers)
    assert no_spec.status_code == 422

    await client.post(f"{API}/admin/doctors", json=doctor_payload([spec.id]), headers=headers)
    dup = await client.post(f"{API}/admin/doctors", json=doctor_payload([spec.id]), headers=headers)
    assert dup.status_code == 409


async def test_list_search_filter_update(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    _, cardio = await make_doctor(session_factory, "c@example.com", specialization="Cardiology")
    _, neuro = await make_doctor(
        session_factory, "n@example.com", specialization="Neurology", first_name="Nina"
    )

    all_docs = await client.get(f"{API}/admin/doctors", headers=headers)
    assert all_docs.json()["total"] == 2

    spec_id = cardio.specializations[0].id
    filtered = await client.get(
        f"{API}/admin/doctors", params={"specialization_id": spec_id}, headers=headers
    )
    assert [d["id"] for d in filtered.json()["items"]] == [cardio.id]

    searched = await client.get(f"{API}/admin/doctors", params={"search": "nina"}, headers=headers)
    assert [d["id"] for d in searched.json()["items"]] == [neuro.id]
    by_spec_name = await client.get(
        f"{API}/admin/doctors", params={"search": "neuro"}, headers=headers
    )
    assert [d["id"] for d in by_spec_name.json()["items"]] == [neuro.id]

    paged = await client.get(f"{API}/admin/doctors", params={"page_size": 1}, headers=headers)
    assert paged.json()["pages"] == 2 and len(paged.json()["items"]) == 1

    updated = await client.patch(
        f"{API}/admin/doctors/{cardio.id}",
        json={"bio": "Updated", "experience_years": 20, "specialization_ids": [spec_id]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["bio"] == "Updated" and updated.json()["experience_years"] == 20


async def test_deactivate_doctor_cancels_future_appointments(
    client: AsyncClient, session_factory
) -> None:
    headers = await admin_headers(client, session_factory)
    _, doctor = await make_doctor(session_factory)
    patient_user, _ = await make_patient(session_factory)
    patient_headers = await login(client, "patient@example.com")
    booked = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient_headers,
    )
    assert booked.status_code == 201

    res = await client.post(
        f"{API}/admin/doctors/{doctor.id}/status",
        json={"is_active": False, "reason": "On sabbatical"},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["cancelled_appointments"] == 1
    assert res.json()["doctor"]["is_active"] is False

    appointment = await client.get(
        f"{API}/appointments/{booked.json()['id']}", headers=patient_headers
    )
    assert appointment.json()["status"] == AppointmentStatus.CANCELLED
    async with session_factory() as db:
        types = list(
            await db.scalars(
                select(Notification.type).where(Notification.user_id == patient_user.id)
            )
        )
    assert "APPOINTMENT_CANCELLED" in types

    blocked = await client.post(
        f"{API}/auth/login",
        json={"email": "doctor@example.com", "password": PASSWORD, "portal": "staff"},
    )
    assert blocked.status_code == 403
    # Inactive doctors disappear from the patient-facing directory.
    directory = await client.get(f"{API}/doctors", headers=patient_headers)
    assert directory.json()["total"] == 0


async def test_soft_delete_and_reset_password(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    _, doctor = await make_doctor(session_factory)
    _, other = await make_doctor(session_factory, "other@example.com")

    reset = await client.post(
        f"{API}/admin/doctors/{other.id}/reset-password",
        json={"temporary_password": "NewTemp99"},
        headers=headers,
    )
    assert reset.status_code == 204
    relogin = await client.post(
        f"{API}/auth/login",
        json={"email": "other@example.com", "password": "NewTemp99", "portal": "staff"},
    )
    assert relogin.json()["must_change_password"] is True

    assert (
        await client.delete(f"{API}/admin/doctors/{doctor.id}", headers=headers)
    ).status_code == 204
    assert (
        await client.get(f"{API}/admin/doctors/{doctor.id}", headers=headers)
    ).status_code == 404


async def test_specialization_management(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    created = await client.post(
        f"{API}/admin/specializations", json={"name": "Dermatology"}, headers=headers
    )
    assert created.status_code == 201
    dup = await client.post(
        f"{API}/admin/specializations", json={"name": "dermatology"}, headers=headers
    )
    assert dup.status_code == 409
    spec_id = created.json()["id"]
    off = await client.patch(
        f"{API}/admin/specializations/{spec_id}", json={"is_active": False}, headers=headers
    )
    assert off.json()["is_active"] is False

    await make_patient(session_factory)
    patient_headers = await login(client, "patient@example.com")
    public = await client.get(f"{API}/specializations", headers=patient_headers)
    assert all(s["name"] != "Dermatology" for s in public.json())


async def test_admin_user_management_and_audit(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    patient_user, _ = await make_patient(session_factory)

    users = await client.get(f"{API}/admin/users", params={"role": "PATIENT"}, headers=headers)
    assert [u["id"] for u in users.json()["items"]] == [patient_user.id]

    off = await client.post(
        f"{API}/admin/users/{patient_user.id}/status", json={"is_active": False}, headers=headers
    )
    assert off.status_code == 200 and off.json()["is_active"] is False

    me = (await client.get(f"{API}/users/me", headers=headers)).json()
    self_off = await client.post(
        f"{API}/admin/users/{me['id']}/status", json={"is_active": False}, headers=headers
    )
    assert self_off.status_code == 400

    logs = await client.get(
        f"{API}/admin/audit-logs", params={"action": "user.deactivated"}, headers=headers
    )
    assert logs.json()["total"] == 1
    assert logs.json()["items"][0]["entity_id"] == str(patient_user.id)
