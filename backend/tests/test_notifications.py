from httpx import AsyncClient

from app.models import NotificationType
from app.services.notification_service import NotificationPayload, Notifier
from tests.helpers import API, iso, login, make_doctor, make_patient, slot_start


async def test_notification_inbox(client: AsyncClient, session_factory) -> None:
    _, doctor = await make_doctor(session_factory)
    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient,
    )
    inbox = await client.get(f"{API}/notifications", headers=patient)
    assert inbox.json()["total"] == 1
    item = inbox.json()["items"][0]
    assert item["type"] == "APPOINTMENT_BOOKED"
    assert item["data"]["appointment_id"]

    count = await client.get(f"{API}/notifications/unread-count", headers=patient)
    assert count.json()["unread"] == 1
    assert (
        await client.post(f"{API}/notifications/{item['id']}/read", headers=patient)
    ).status_code == 204
    assert (await client.get(f"{API}/notifications/unread-count", headers=patient)).json()[
        "unread"
    ] == 0

    doctor_h = await login(client, "doctor@example.com", portal="staff")
    # Users only ever see their own notifications.
    assert (
        await client.post(f"{API}/notifications/{item['id']}/read", headers=doctor_h)
    ).status_code == 204
    assert (await client.get(f"{API}/notifications", headers=doctor_h)).json()["total"] == 1
    await client.post(f"{API}/notifications/read-all", headers=doctor_h)
    unread = await client.get(
        f"{API}/notifications", params={"unread_only": True}, headers=doctor_h
    )
    assert unread.json()["total"] == 0


async def test_dedupe_key_prevents_duplicates(session_factory) -> None:
    user, _ = await make_patient(session_factory)
    payload = NotificationPayload(NotificationType.ACCOUNT, "Hello", "Body", dedupe_key="welcome")
    for _ in range(2):
        async with session_factory() as db:
            notifier = Notifier(db)
            await notifier.add(user.id, payload)
            await db.commit()
    async with session_factory() as db:
        from sqlalchemy import func, select

        from app.models import Notification

        count = await db.scalar(select(func.count()).select_from(Notification))
    assert count == 1


async def test_meta_endpoint(client: AsyncClient) -> None:
    res = await client.get(f"{API}/meta")
    assert res.status_code == 200
    body = res.json()
    assert body["clinic_timezone"] == "Asia/Kolkata"
    assert body["appointment_duration_minutes"] == 30
    assert "secret" not in res.text.lower()
