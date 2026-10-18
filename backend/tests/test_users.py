from httpx import AsyncClient

from tests.fakes import JPEG_BYTES, PNG_BYTES, FakeStorage
from tests.helpers import API, login, make_doctor, make_patient


async def test_read_me_patient(client: AsyncClient, session_factory) -> None:
    user, patient_id = await make_patient(session_factory, "patient@example.com")
    headers = await login(client, "patient@example.com")

    res = await client.get(f"{API}/users/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == user.id
    assert body["email"] == "patient@example.com"
    assert body["role"] == "PATIENT"
    assert body["patient"] is not None
    assert body["patient"]["id"] == patient_id
    assert body["doctor_id"] is None


async def test_read_me_doctor(client: AsyncClient, session_factory) -> None:
    user, doctor = await make_doctor(session_factory, "doctor@example.com")
    headers = await login(client, "doctor@example.com", portal="staff")

    res = await client.get(f"{API}/users/me", headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == user.id
    assert body["role"] == "DOCTOR"
    assert body["doctor_id"] == doctor.id
    assert body["patient"] is None


async def test_update_me_patient(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory, "patient@example.com")
    headers = await login(client, "patient@example.com")

    payload = {
        "first_name": "Aarav",
        "last_name": "Sharma",
        "phone": "+91 91234 56789",
        "date_of_birth": "1995-05-15",
        "gender": "male",
        "emergency_contact_name": "Rohan Sharma",
        "emergency_contact_phone": "+91 99887 76655",
    }
    res = await client.patch(f"{API}/users/me", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["first_name"] == "Aarav"
    assert body["last_name"] == "Sharma"
    assert body["phone"] == "+91 91234 56789"
    assert body["patient"]["date_of_birth"] == "1995-05-15"
    assert body["patient"]["gender"] == "male"
    assert body["patient"]["emergency_contact_name"] == "Rohan Sharma"
    assert body["patient"]["emergency_contact_phone"] == "+91 99887 76655"


async def test_update_me_doctor_ignores_patient_fields(client: AsyncClient, session_factory) -> None:
    await make_doctor(session_factory, "doctor@example.com")
    headers = await login(client, "doctor@example.com", portal="staff")

    payload = {
        "first_name": "Siddharth",
        "last_name": "Verma",
        "phone": "+91 98765 00000",
        "gender": "male",
    }
    res = await client.patch(f"{API}/users/me", json=payload, headers=headers)
    assert res.status_code == 200
    body = res.json()
    assert body["first_name"] == "Siddharth"
    assert body["last_name"] == "Verma"
    assert body["phone"] == "+91 98765 00000"
    assert body["patient"] is None


async def test_upload_and_delete_avatar(
    client: AsyncClient, session_factory, storage: FakeStorage
) -> None:
    await make_patient(session_factory, "patient@example.com")
    headers = await login(client, "patient@example.com")

    # 1. Upload first avatar
    upload_res = await client.post(
        f"{API}/users/me/avatar",
        files={"file": ("profile.png", PNG_BYTES, "image/png")},
        headers=headers,
    )
    assert upload_res.status_code == 200
    body = upload_res.json()
    assert body["avatar_url"] is not None
    assert "onezae/avatars" in body["avatar_url"]
    first_url = body["avatar_url"]
    assert len(storage.uploads) == 1

    # 2. Upload replacement avatar -> deletes previous one
    upload_res2 = await client.post(
        f"{API}/users/me/avatar",
        files={"file": ("profile2.jpg", JPEG_BYTES, "image/jpeg")},
        headers=headers,
    )
    assert upload_res2.status_code == 200
    body2 = upload_res2.json()
    assert body2["avatar_url"] != first_url
    assert len(storage.uploads) == 2
    assert len(storage.deleted) == 1

    # 3. Delete avatar
    delete_res = await client.delete(f"{API}/users/me/avatar", headers=headers)
    assert delete_res.status_code == 204
    assert len(storage.deleted) == 2

    # 4. Profile now has null avatar_url
    me_res = await client.get(f"{API}/users/me", headers=headers)
    assert me_res.json()["avatar_url"] is None


async def test_upload_avatar_invalid_file(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory, "patient@example.com")
    headers = await login(client, "patient@example.com")

    res = await client.post(
        f"{API}/users/me/avatar",
        files={"file": ("fake.png", b"not-image-bytes", "image/png")},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "unsupported_type"
