import pytest
from httpx import AsyncClient

from scripts import seed
from tests.helpers import API


async def test_seeded_demo_accounts_can_sign_in(
    client: AsyncClient, session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: demo emails must pass the API's email validation (reserved
    TLDs such as .local are rejected), otherwise nobody can log in."""
    monkeypatch.setattr(seed, "SessionLocal", session_factory)
    await seed.seed_demo("DemoPass1")
    await seed.seed_demo("DemoPass1")  # idempotent

    for email, portal in (
        ("admin.demo@example.com", "staff"),
        ("anita.rao.demo@example.com", "staff"),
        ("patient.demo@example.com", "patient"),
    ):
        res = await client.post(
            f"{API}/auth/login", json={"email": email, "password": "DemoPass1", "portal": portal}
        )
        assert res.status_code == 200, (email, res.text)

    patient = await client.post(
        f"{API}/auth/login",
        json={"email": "patient.demo@example.com", "password": "DemoPass1"},
    )
    headers = {"Authorization": f"Bearer {patient.json()['access_token']}"}
    doctors = await client.get(f"{API}/doctors", headers=headers)
    assert doctors.json()["total"] == 4
