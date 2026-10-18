import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Role, User
from scripts import create_admin, seed, seed_defaults, send_reminders
from tests.helpers import API


async def test_seed_defaults_script(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(seed, "SessionLocal", session_factory)
    monkeypatch.setattr(seed_defaults, "SessionLocal", session_factory)

    # Run seed_defaults twice to verify idempotence
    await seed_defaults.seed_defaults()
    await seed_defaults.seed_defaults()

    # Verify admin can log in
    admin_login = await client.post(
        f"{API}/auth/login",
        json={"email": seed_defaults.ADMIN_EMAIL, "password": seed_defaults.ADMIN_PASSWORD, "portal": "staff"},
    )
    assert admin_login.status_code == 200
    assert admin_login.json()["role"] == "ADMIN"

    # Verify doctor can log in
    doctor_login = await client.post(
        f"{API}/auth/login",
        json={"email": seed_defaults.DOCTOR_EMAIL, "password": seed_defaults.DOCTOR_PASSWORD, "portal": "staff"},
    )
    assert doctor_login.status_code == 200
    assert doctor_login.json()["role"] == "DOCTOR"

    # Verify patient can log in
    patient_login = await client.post(
        f"{API}/auth/login",
        json={"email": seed_defaults.PATIENT_EMAIL, "password": seed_defaults.PATIENT_PASSWORD, "portal": "patient"},
    )
    assert patient_login.status_code == 200
    assert patient_login.json()["role"] == "PATIENT"


async def test_create_admin_script(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(create_admin, "SessionLocal", session_factory)
    # Mock getpass
    monkeypatch.setattr("getpass.getpass", lambda prompt: "CustomAdminPass1")

    # Run create_admin main
    await create_admin.main("customadmin@example.com", "Super", "Admin")

    async with session_factory() as db:
        user = await db.scalar(select(User).where(User.email == "customadmin@example.com"))
    assert user is not None
    assert user.role == Role.ADMIN

    # Sign in
    res = await client.post(
        f"{API}/auth/login",
        json={"email": "customadmin@example.com", "password": "CustomAdminPass1", "portal": "staff"},
    )
    assert res.status_code == 200
    assert res.json()["role"] == "ADMIN"


async def test_send_reminders_script(
    session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(send_reminders, "SessionLocal", session_factory)
    # Calling main should not raise any error
    await send_reminders.main()
