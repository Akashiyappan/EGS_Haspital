import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.integrations.storage import get_storage
from tests.fakes import JPEG_BYTES, PNG_BYTES, FakeStorage
from tests.helpers import API, iso, login, make_doctor, make_patient, slot_start


@pytest.fixture
async def care(client: AsyncClient, session_factory):  # type: ignore[no-untyped-def]
    """A doctor and a patient with a booked appointment (care relationship)."""
    doctor_user, doctor = await make_doctor(session_factory)
    patient_user, patient_id = await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    doctor_h = await login(client, "doctor@example.com", portal="staff")
    res = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(slot_start())},
        headers=patient,
    )
    assert res.status_code == 201
    return {
        "doctor": doctor,
        "doctor_user": doctor_user,
        "patient_user": patient_user,
        "patient_id": patient_id,
        "patient": patient,
        "doctor_h": doctor_h,
    }


async def open_conversation(client: AsyncClient, care) -> int:  # type: ignore[no-untyped-def]
    res = await client.post(
        f"{API}/chat/conversations", json={"doctor_id": care["doctor"].id}, headers=care["patient"]
    )
    assert res.status_code == 200, res.text
    return int(res.json()["id"])


async def test_chat_requires_care_relationship(client: AsyncClient, session_factory) -> None:
    _, doctor = await make_doctor(session_factory)
    await make_patient(session_factory)
    patient = await login(client, "patient@example.com")
    res = await client.post(
        f"{API}/chat/conversations", json={"doctor_id": doctor.id}, headers=patient
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "no_care_relationship"


async def test_send_and_read_messages(client: AsyncClient, care) -> None:
    conversation_id = await open_conversation(client, care)
    again = await open_conversation(client, care)
    assert again == conversation_id  # one thread per doctor-patient pair

    url = f"{API}/chat/conversations/{conversation_id}/messages"
    sent = await client.post(url, json={"body": "Hello doctor"}, headers=care["patient"])
    assert sent.status_code == 201
    reply = await client.post(
        url, json={"body": "Hello, how can I help?"}, headers=care["doctor_h"]
    )
    assert reply.status_code == 201

    history = await client.get(url, headers=care["patient"])
    assert [m["body"] for m in history.json()["items"]] == [
        "Hello doctor",
        "Hello, how can I help?",
    ]

    doctor_list = await client.get(f"{API}/chat/conversations", headers=care["doctor_h"])
    item = doctor_list.json()["items"][0]
    assert item["unread_count"] == 1
    assert item["counterpart"]["patient_id"] == care["patient_id"]
    assert item["last_message"]["body"] == "Hello, how can I help?"

    unread = await client.get(f"{API}/chat/unread-count", headers=care["doctor_h"])
    assert unread.json()["unread"] == 1
    marked = await client.post(
        f"{API}/chat/conversations/{conversation_id}/read",
        json={"message_id": sent.json()["id"]},
        headers=care["doctor_h"],
    )
    assert marked.status_code == 204
    assert (await client.get(f"{API}/chat/unread-count", headers=care["doctor_h"])).json()[
        "unread"
    ] == 0


async def test_doctor_can_start_conversation(client: AsyncClient, care) -> None:
    res = await client.post(
        f"{API}/chat/conversations",
        json={"patient_id": care["patient_id"]},
        headers=care["doctor_h"],
    )
    assert res.status_code == 200
    assert res.json()["counterpart"]["role"] == "PATIENT"


async def test_message_pagination_and_catch_up(client: AsyncClient, care) -> None:
    conversation_id = await open_conversation(client, care)
    url = f"{API}/chat/conversations/{conversation_id}/messages"
    ids = []
    for i in range(5):
        res = await client.post(url, json={"body": f"m{i}"}, headers=care["patient"])
        ids.append(res.json()["id"])

    latest = await client.get(url, params={"limit": 2}, headers=care["patient"])
    assert [m["body"] for m in latest.json()["items"]] == ["m3", "m4"]
    assert latest.json()["has_more"] is True
    older = await client.get(url, params={"limit": 2, "before_id": ids[3]}, headers=care["patient"])
    assert [m["body"] for m in older.json()["items"]] == ["m1", "m2"]
    missed = await client.get(url, params={"after_id": ids[2]}, headers=care["patient"])
    assert [m["body"] for m in missed.json()["items"]] == ["m3", "m4"]


async def test_send_is_idempotent(client: AsyncClient, care) -> None:
    conversation_id = await open_conversation(client, care)
    url = f"{API}/chat/conversations/{conversation_id}/messages"
    payload = {"body": "Only once", "client_id": "abc-123"}
    first = await client.post(url, json=payload, headers=care["patient"])
    second = await client.post(url, json=payload, headers=care["patient"])
    assert first.json()["id"] == second.json()["id"]
    history = await client.get(url, headers=care["patient"])
    assert len(history.json()["items"]) == 1


async def test_outsiders_cannot_access_conversation(
    client: AsyncClient, session_factory, care
) -> None:
    conversation_id = await open_conversation(client, care)
    await make_patient(session_factory, "nosy@example.com")
    nosy = await login(client, "nosy@example.com")
    url = f"{API}/chat/conversations/{conversation_id}/messages"
    assert (await client.get(url, headers=nosy)).status_code == 404
    assert (await client.post(url, json={"body": "hi"}, headers=nosy)).status_code == 404


async def test_send_image(client: AsyncClient, care, storage: FakeStorage) -> None:
    conversation_id = await open_conversation(client, care)
    res = await client.post(
        f"{API}/chat/conversations/{conversation_id}/images",
        files={"file": ("rash.png", PNG_BYTES, "image/png")},
        data={"caption": "Rash on my arm"},
        headers=care["patient"],
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["message_type"] == "IMAGE"
    assert body["body"] == "Rash on my arm"
    attachment = body["attachments"][0]
    assert attachment["url"].startswith("https://res.cloudinary.test/image/authenticated/")
    assert storage.uploads[0]["private"] is True


async def test_image_validation(client: AsyncClient, care, monkeypatch: pytest.MonkeyPatch) -> None:
    conversation_id = await open_conversation(client, care)
    url = f"{API}/chat/conversations/{conversation_id}/images"

    # Content is sniffed: a text file renamed .png is rejected.
    fake = await client.post(
        url, files={"file": ("x.png", b"not an image at all", "image/png")}, headers=care["patient"]
    )
    assert fake.status_code == 400
    assert fake.json()["error"]["code"] == "unsupported_type"

    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 100)
    big = await client.post(
        url, files={"file": ("big.jpg", JPEG_BYTES, "image/jpeg")}, headers=care["patient"]
    )
    assert big.status_code == 413


async def test_uploads_not_configured(client: AsyncClient, app, care) -> None:  # type: ignore[no-untyped-def]
    del app.dependency_overrides[get_storage]
    conversation_id = await open_conversation(client, care)
    res = await client.post(
        f"{API}/chat/conversations/{conversation_id}/images",
        files={"file": ("a.png", PNG_BYTES, "image/png")},
        headers=care["patient"],
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "uploads_not_configured"


async def test_message_notification_is_not_duplicated(client: AsyncClient, care) -> None:
    conversation_id = await open_conversation(client, care)
    url = f"{API}/chat/conversations/{conversation_id}/messages"
    for i in range(3):
        await client.post(url, json={"body": f"msg {i}"}, headers=care["patient"])
    notes = await client.get(f"{API}/notifications", headers=care["doctor_h"])
    new_message = [n for n in notes.json()["items"] if n["type"] == "NEW_MESSAGE"]
    assert len(new_message) == 1  # one per unread streak
    assert "msg" not in new_message[0]["body"]  # message content is not copied into notifications


def test_websocket_delivery_and_auth(app, care) -> None:  # type: ignore[no-untyped-def]
    """Realtime: authenticated sockets receive message events; unauthenticated
    sockets are closed with 4401."""
    with TestClient(app) as sync_client:
        patient_token = care["patient"]["Authorization"].removeprefix("Bearer ")
        doctor_token = care["doctor_h"]["Authorization"].removeprefix("Bearer ")
        conversation = sync_client.post(
            f"{API}/chat/conversations",
            json={"doctor_id": care["doctor"].id},
            headers=care["patient"],
        ).json()

        with sync_client.websocket_connect(f"{API}/ws") as anon:
            anon.send_json({"type": "auth", "token": "garbage"})
            with pytest.raises(WebSocketDisconnect) as closed:
                anon.receive_json()
            assert closed.value.code == 4401

        with sync_client.websocket_connect(f"{API}/ws") as doctor_ws:
            doctor_ws.send_json({"type": "auth", "token": doctor_token})
            assert doctor_ws.receive_json()["type"] == "ready"
            doctor_ws.send_json({"type": "ping"})
            assert doctor_ws.receive_json()["type"] == "pong"

            with sync_client.websocket_connect(f"{API}/ws") as patient_ws:
                patient_ws.send_json({"type": "auth", "token": patient_token})
                assert patient_ws.receive_json()["type"] == "ready"
                presence = doctor_ws.receive_json()
                assert presence == {
                    "type": "presence",
                    "data": {"user_id": care["patient_user"].id, "online": True},
                }

                patient_ws.send_json(
                    {"type": "typing", "data": {"conversation_id": conversation["id"]}}
                )
                assert doctor_ws.receive_json()["type"] == "typing"

                sync_client.post(
                    f"{API}/chat/conversations/{conversation['id']}/messages",
                    json={"body": "Realtime hello"},
                    headers=care["patient"],
                )
                events = [doctor_ws.receive_json() for _ in range(2)]
                kinds = {e["type"] for e in events}
                assert kinds == {"message.created", "notification.created"}
                message = next(e for e in events if e["type"] == "message.created")
                assert message["data"]["body"] == "Realtime hello"
