from datetime import timedelta

from httpx import AsyncClient

from app.core.timeutils import utcnow
from tests.fakes import PNG_BYTES, FakeStorage
from tests.helpers import (
    API,
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


async def test_admin_stats(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    _, doc1 = await make_doctor(session_factory, "d1@example.com")
    _, doc2 = await make_doctor(session_factory, "d2@example.com")
    _patient_user, _patient_id = await make_patient(session_factory, "p1@example.com")

    # Deactivate one doctor
    await client.post(
        f"{API}/admin/doctors/{doc2.id}/status",
        json={"is_active": False, "reason": "Inactive"},
        headers=headers,
    )

    # Book an appointment
    patient_h = await login(client, "p1@example.com")
    await client.post(
        f"{API}/appointments",
        json={"doctor_id": doc1.id, "starts_at": iso(slot_start())},
        headers=patient_h,
    )

    res = await client.get(f"{API}/admin/stats", headers=headers)
    assert res.status_code == 200
    stats = res.json()
    assert stats["doctors_active"] == 1
    assert stats["doctors_inactive"] == 1
    assert stats["patients"] == 1
    assert stats["appointments_upcoming"] >= 1
    assert "BOOKED" in stats["appointments_by_status"]


async def test_admin_doctor_avatar_upload(
    client: AsyncClient, session_factory, storage: FakeStorage
) -> None:
    headers = await admin_headers(client, session_factory)
    _, doctor = await make_doctor(session_factory, "doc@example.com")

    res = await client.post(
        f"{API}/admin/doctors/{doctor.id}/avatar",
        files={"file": ("doc_avatar.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["avatar_url"] is not None
    assert "onezae/avatars" in body["avatar_url"]
    assert len(storage.uploads) == 1

    # Overwrite avatar
    res2 = await client.post(
        f"{API}/admin/doctors/{doctor.id}/avatar",
        files={"file": ("doc_avatar2.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert res2.status_code == 200
    assert len(storage.uploads) == 2
    assert len(storage.deleted) == 1


async def test_admin_time_off_management(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)
    _, doctor = await make_doctor(session_factory, "doc@example.com")

    now = utcnow()
    start = now + timedelta(days=2)
    end = start + timedelta(days=1)

    # 1. Create doctor-specific time off
    doc_time_off = await client.post(
        f"{API}/admin/doctors/{doctor.id}/time-off",
        json={"kind": "LEAVE", "starts_at": iso(start), "ends_at": iso(end), "reason": "Conference"},
        headers=headers,
    )
    assert doc_time_off.status_code == 201
    doc_to_id = doc_time_off.json()["id"]

    # 2. Get doctor-specific time off
    doc_to_list = await client.get(f"{API}/admin/doctors/{doctor.id}/time-off", headers=headers)
    assert doc_to_list.status_code == 200
    assert any(t["id"] == doc_to_id for t in doc_to_list.json())

    # 3. Create clinic-wide holiday
    h_start = now + timedelta(days=5)
    h_end = h_start + timedelta(days=1)
    clinic_holiday = await client.post(
        f"{API}/admin/time-off",
        json={"kind": "HOLIDAY", "starts_at": iso(h_start), "ends_at": iso(h_end), "reason": "National Holiday"},
        headers=headers,
    )
    assert clinic_holiday.status_code == 201
    holiday_id = clinic_holiday.json()["id"]

    # 4. List clinic-wide time offs
    clinic_list = await client.get(f"{API}/admin/time-off", headers=headers)
    assert clinic_list.status_code == 200
    assert any(t["id"] == holiday_id for t in clinic_list.json())

    # 5. Delete time off
    del_res = await client.delete(f"{API}/admin/time-off/{holiday_id}", headers=headers)
    assert del_res.status_code == 204

    # 6. Verify deleted
    clinic_list2 = await client.get(f"{API}/admin/time-off", headers=headers)
    assert all(t["id"] != holiday_id for t in clinic_list2.json())


async def test_admin_specializations_extended(client: AsyncClient, session_factory) -> None:
    headers = await admin_headers(client, session_factory)

    # List all specializations in admin
    spec = await make_specialization(session_factory, "Orthopedics")
    res = await client.get(f"{API}/admin/specializations", headers=headers)
    assert res.status_code == 200
    names = [s["name"] for s in res.json()]
    assert "Orthopedics" in names

    # Patch specialization description and active status
    patch_res = await client.patch(
        f"{API}/admin/specializations/{spec.id}",
        json={"description": "Bones and joints specialist", "is_active": False},
        headers=headers,
    )
    assert patch_res.status_code == 200
    body = patch_res.json()
    assert body["description"] == "Bones and joints specialist"
    assert body["is_active"] is False
