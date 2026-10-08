import re

import pytest
from httpx import AsyncClient

from app.core import rate_limit
from app.core.config import settings
from app.integrations.email import EmailMessage
from app.models import Role
from tests.helpers import API, PASSWORD, login, make_admin, make_doctor, make_patient, make_user

REGISTER = {"first_name": " Priya ", "email": "Priya@Example.com", "password": "Secur3pass"}


async def test_register_creates_patient(client: AsyncClient) -> None:
    res = await client.post(f"{API}/auth/register", json=REGISTER)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["role"] == "PATIENT"
    assert body["email"] == "priya@example.com"
    assert body["first_name"] == "Priya"
    assert "hashed_password" not in body and "password" not in body


async def test_register_ignores_role_in_payload(client: AsyncClient) -> None:
    res = await client.post(f"{API}/auth/register", json={**REGISTER, "role": "ADMIN"})
    assert res.status_code == 201
    assert res.json()["role"] == "PATIENT"


async def test_register_duplicate_email(client: AsyncClient) -> None:
    assert (await client.post(f"{API}/auth/register", json=REGISTER)).status_code == 201
    res = await client.post(f"{API}/auth/register", json=REGISTER)
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({**REGISTER, "password": "short1"}, "password"),
        ({**REGISTER, "password": "lettersonly"}, "password"),
        ({**REGISTER, "email": "not-an-email"}, "email"),
        ({**REGISTER, "first_name": "   "}, "first_name"),
    ],
)
async def test_register_validation(client: AsyncClient, payload: dict, field: str) -> None:
    res = await client.post(f"{API}/auth/register", json=payload)
    assert res.status_code == 422
    assert res.json()["error"]["details"][0]["loc"][-1] == field


async def test_patient_login_and_me(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    me = await client.get(f"{API}/users/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "PATIENT"
    assert me.json()["patient"] is not None


async def test_portals_are_separated(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    await make_admin(session_factory)
    patient_on_staff = await client.post(
        f"{API}/auth/login",
        json={"email": "patient@example.com", "password": PASSWORD, "portal": "staff"},
    )
    admin_on_patient = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@example.com", "password": PASSWORD, "portal": "patient"},
    )
    # Wrong portal is indistinguishable from wrong credentials.
    for res in (patient_on_staff, admin_on_patient):
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "invalid_credentials"
    staff = await client.post(
        f"{API}/auth/login",
        json={"email": "admin@example.com", "password": PASSWORD, "portal": "staff"},
    )
    assert staff.status_code == 200
    assert staff.json()["role"] == "ADMIN"


async def test_invalid_credentials(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    for email, password in (
        ("patient@example.com", "wrong-pass1"),
        ("ghost@example.com", PASSWORD),
    ):
        res = await client.post(f"{API}/auth/login", json={"email": email, "password": password})
        assert res.status_code == 401
        assert res.json()["error"]["code"] == "invalid_credentials"


async def test_inactive_user_cannot_login(client: AsyncClient, session_factory) -> None:
    await make_user(session_factory, Role.PATIENT, "off@example.com", is_active=False)
    res = await client.post(
        f"{API}/auth/login", json={"email": "off@example.com", "password": PASSWORD}
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "inactive_user"


async def test_login_sets_httponly_refresh_cookie(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    res = await client.post(
        f"{API}/auth/login", json={"email": "patient@example.com", "password": PASSWORD}
    )
    cookie = res.headers["set-cookie"]
    assert "refresh_token=" in cookie and "HttpOnly" in cookie and f"Path={API}/auth" in cookie
    assert res.headers["cache-control"] == "no-store"


async def test_refresh_and_logout_revokes(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    refreshed = await client.post(f"{API}/auth/refresh")
    assert refreshed.status_code == 200
    old_refresh = client.cookies.get("refresh_token")

    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    assert (await client.get(f"{API}/users/me", headers=headers)).status_code == 401
    client.cookies.set("refresh_token", old_refresh, path=f"{API}/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_refresh_token_is_not_an_access_token(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    await login(client, "patient@example.com")
    refresh = client.cookies.get("refresh_token")
    res = await client.get(f"{API}/users/me", headers={"Authorization": f"Bearer {refresh}"})
    assert res.status_code == 401


async def test_temporary_password_must_be_changed(client: AsyncClient, session_factory) -> None:
    await make_user(session_factory, Role.DOCTOR, "temp@example.com", must_change_password=True)
    login_res = await client.post(
        f"{API}/auth/login",
        json={"email": "temp@example.com", "password": PASSWORD, "portal": "staff"},
    )
    assert login_res.json()["must_change_password"] is True
    headers = {"Authorization": f"Bearer {login_res.json()['access_token']}"}

    blocked = await client.get(f"{API}/appointments", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "password_change_required"
    assert (await client.get(f"{API}/users/me", headers=headers)).status_code == 200

    changed = await client.post(
        f"{API}/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "BrandN3wPass"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    new_headers = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert (await client.get(f"{API}/appointments", headers=new_headers)).status_code == 200
    # Old token was revoked by the password change.
    assert (await client.get(f"{API}/users/me", headers=headers)).status_code == 401


async def test_change_password_requires_current(client: AsyncClient, session_factory) -> None:
    await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    res = await client.post(
        f"{API}/auth/change-password",
        json={"current_password": "Wrong1234", "new_password": "BrandN3wPass"},
        headers=headers,
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "invalid_current_password"


async def test_forgot_and_reset_password(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_patient(session_factory)
    sent: list[EmailMessage] = []

    class Capture:
        async def send(self, message: EmailMessage) -> None:
            sent.append(message)

    monkeypatch.setattr("app.services.auth_service.get_email_sender", lambda: Capture())

    unknown = await client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"})
    known = await client.post(f"{API}/auth/forgot-password", json={"email": "patient@example.com"})
    assert unknown.status_code == known.status_code == 202
    assert unknown.json() == known.json()  # no account enumeration
    assert len(sent) == 1

    token = re.search(r"token=([\w.-]+)", sent[0].text).group(1)  # type: ignore[union-attr]
    reset = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": "Reset3dPass"}
    )
    assert reset.status_code == 200
    await login(client, "patient@example.com", password="Reset3dPass")

    reused = await client.post(
        f"{API}/auth/reset-password", json={"token": token, "new_password": "Another1Pass"}
    )
    assert reused.status_code == 400
    assert reused.json()["error"]["code"] == "invalid_reset_token"


async def test_auth_rate_limit(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    await make_patient(session_factory)
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    rate_limit.backend.reset()  # type: ignore[attr-defined]
    limit, _ = rate_limit.parse_rate(settings.RATE_LIMIT_AUTH)
    payload = {"email": "patient@example.com", "password": "wrong-pass1"}
    statuses = [
        (await client.post(f"{API}/auth/login", json=payload)).status_code for _ in range(limit + 1)
    ]
    assert statuses[:limit] == [401] * limit
    assert statuses[-1] == 429


async def test_doctor_and_admin_login_on_staff_portal(client: AsyncClient, session_factory) -> None:
    await make_doctor(session_factory)
    res = await client.post(
        f"{API}/auth/login",
        json={"email": "doctor@example.com", "password": PASSWORD, "portal": "staff"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "DOCTOR"
