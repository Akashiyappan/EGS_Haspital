from httpx import AsyncClient

from tests.helpers import (
    API,
    iso,
    login,
    make_doctor,
    make_patient,
    slot_start,
)


async def test_doctor_profile_and_update(client: AsyncClient, session_factory) -> None:
    _, doctor = await make_doctor(session_factory, "doctor@example.com")
    headers = await login(client, "doctor@example.com", portal="staff")

    # Get own profile
    res = await client.get(f"{API}/doctor/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == doctor.id
    assert body["qualification"] == "MBBS"
    assert body["bio"] is None

    # Update own bio and qualification
    update_res = await client.patch(
        f"{API}/doctor/me",
        json={"bio": "Specialist in heart disease.", "qualification": "MBBS, MD, DM"},
        headers=headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["bio"] == "Specialist in heart disease."
    assert updated["qualification"] == "MBBS, MD, DM"


async def test_doctor_schedule_view(client: AsyncClient, session_factory) -> None:
    _, _doctor = await make_doctor(session_factory, "doctor@example.com")
    headers = await login(client, "doctor@example.com", portal="staff")

    res = await client.get(f"{API}/doctor/schedule", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["timezone"] == "Asia/Kolkata"
    assert len(body["rules"]) > 0
    assert isinstance(body["time_off"], list)


async def test_doctor_patients_list_and_detail(client: AsyncClient, session_factory) -> None:
    _, doctor = await make_doctor(session_factory, "doctor@example.com")
    _patient_user, patient_id = await make_patient(session_factory, "patient@example.com")
    doctor_h = await login(client, "doctor@example.com", portal="staff")
    patient_h = await login(client, "patient@example.com")

    # Before booking, doctor has no patients
    empty = await client.get(f"{API}/doctor/patients", headers=doctor_h)
    assert empty.status_code == 200
    assert empty.json()["total"] == 0

    # Book an appointment
    book_res = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient_h,
    )
    assert book_res.status_code == 201

    # Now doctor sees this patient
    patients_res = await client.get(f"{API}/doctor/patients", headers=doctor_h)
    assert patients_res.status_code == 200
    body = patients_res.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == patient_id
    assert body["items"][0]["email"] == "patient@example.com"
    assert body["items"][0]["appointment_count"] == 1

    # Search filter
    search_hit = await client.get(
        f"{API}/doctor/patients", params={"search": "Pat"}, headers=doctor_h
    )
    assert search_hit.json()["total"] == 1
    search_miss = await client.get(
        f"{API}/doctor/patients", params={"search": "Nonexistent"}, headers=doctor_h
    )
    assert search_miss.json()["total"] == 0

    # Detail of own patient
    detail_res = await client.get(f"{API}/doctor/patients/{patient_id}", headers=doctor_h)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == patient_id
    assert detail["email"] == "patient@example.com"


async def test_doctor_cannot_view_unrelated_patient_detail(
    client: AsyncClient, session_factory
) -> None:
    _, _doctor = await make_doctor(session_factory, "doctor@example.com")
    _, stranger_id = await make_patient(session_factory, "stranger@example.com")
    doctor_h = await login(client, "doctor@example.com", portal="staff")

    # Detail request for stranger patient returns 404
    res = await client.get(f"{API}/doctor/patients/{stranger_id}", headers=doctor_h)
    assert res.status_code == 404

    # Nonexistent patient ID returns 404
    res_none = await client.get(f"{API}/doctor/patients/99999", headers=doctor_h)
    assert res_none.status_code == 404
