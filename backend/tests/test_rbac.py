import pytest
from httpx import AsyncClient

from app.core.security import create_access_token
from tests.helpers import API, login, make_admin, make_doctor, make_patient

ADMIN_ENDPOINTS = [
    ("GET", "/admin/doctors"),
    ("POST", "/admin/doctors"),
    ("GET", "/admin/users"),
    ("GET", "/admin/stats"),
    ("GET", "/admin/audit-logs"),
    ("PUT", "/admin/doctors/1/schedule"),
    ("POST", "/admin/specializations"),
]


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_admin_endpoints_require_auth(client: AsyncClient, method: str, path: str) -> None:
    res = await client.request(method, f"{API}{path}", json={})
    assert res.status_code == 401


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_patient_cannot_access_admin(
    client: AsyncClient, session_factory, method: str, path: str
) -> None:
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    res = await client.request(method, f"{API}{path}", json={}, headers=headers)
    assert res.status_code == 403


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_doctor_cannot_access_admin(
    client: AsyncClient, session_factory, method: str, path: str
) -> None:
    await make_doctor(session_factory)
    headers = await login(client, "doctor@example.com", portal="staff")
    res = await client.request(method, f"{API}{path}", json={}, headers=headers)
    assert res.status_code == 403


async def test_role_claim_in_token_is_not_trusted(client: AsyncClient, session_factory) -> None:
    user, _ = await make_patient(session_factory)
    forged = create_access_token(user.id, user.token_version, "ADMIN")
    res = await client.get(f"{API}/admin/doctors", headers={"Authorization": f"Bearer {forged}"})
    assert res.status_code == 403


async def test_patient_cannot_use_doctor_portal(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    assert (await client.get(f"{API}/doctor/patients", headers=headers)).status_code == 403


async def test_doctor_and_admin_cannot_book_or_use_ai(client: AsyncClient, session_factory) -> None:
    await make_doctor(session_factory)
    await make_admin(session_factory)
    for email in ("doctor@example.com", "admin@example.com"):
        headers = await login(client, email, portal="staff")
        book = await client.post(
            f"{API}/appointments",
            json={"doctor_id": 1, "starts_at": "2030-01-01T08:00:00Z"},
            headers=headers,
        )
        assert book.status_code == 403
        assert (await client.get(f"{API}/ai/conversations", headers=headers)).status_code == 403


async def test_admin_can_access_admin(client: AsyncClient, session_factory) -> None:
    await make_admin(session_factory)
    headers = await login(client, "admin@example.com", portal="staff")
    assert (await client.get(f"{API}/admin/stats", headers=headers)).status_code == 200
