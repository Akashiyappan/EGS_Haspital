
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Appointment, AppointmentStatus
from tests.helpers import API, login, make_doctor, make_patient, make_specialization, slot_start


@pytest.fixture
async def ai_setup(client: AsyncClient, session_factory):  # type: ignore[no-untyped-def]
    _, cardiologist = await make_doctor(
        session_factory, "cardio@example.com", specialization="Cardiology", first_name="Carter"
    )
    _, gp = await make_doctor(
        session_factory, "gp@example.com", specialization="General Medicine", first_name="Gina"
    )
    await make_specialization(session_factory, "ENT")
    _user, patient_id = await make_patient(session_factory)
    headers = await login(client, "patient@example.com")
    conv_res = await client.post(f"{API}/ai/conversations", json={}, headers=headers)
    assert conv_res.status_code == 201
    conv_id = conv_res.json()["id"]
    return {
        "headers": headers,
        "cardiologist": cardiologist,
        "gp": gp,
        "patient_id": patient_id,
        "conv_id": conv_id,
        "url": f"{API}/ai/conversations/{conv_id}/messages",
    }


async def ask(client: AsyncClient, ai_setup, text: str):  # type: ignore[no-untyped-def]
    return await client.post(ai_setup["url"], json={"content": text}, headers=ai_setup["headers"])


async def test_langgraph_booking_missing_doctor_gathers_specialty(
    client: AsyncClient, ai_setup
) -> None:
    """When user asks to book without specifying doctor or specialty, LangGraph gathers specialty."""
    res = await ask(client, ai_setup, "I want to book an appointment")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["response_type"] == "appointment"
    assert "Cardiology" in result["recommended_specializations"] or "General Medicine" in result["recommended_specializations"]
    assert "specialization" in result["summary"].lower() or "doctor" in result["summary"].lower()


async def test_langgraph_booking_doctor_known_missing_date_gathers_date(
    client: AsyncClient, ai_setup
) -> None:
    """When doctor is known but date is missing, LangGraph checks upcoming availability and asks for date."""
    res = await ask(client, ai_setup, "I want to book an appointment with Dr. Gina")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["response_type"] == "appointment"
    assert result["recommended_doctor_ids"] == [ai_setup["gp"].id]
    assert "Gina" in result["summary"]
    assert "date" in result["summary"].lower() or "day" in result["summary"].lower()


async def test_langgraph_booking_doctor_and_date_known_offers_slots(
    client: AsyncClient, ai_setup
) -> None:
    """When doctor and date are known, LangGraph retrieves live slots and offers them."""
    res = await ask(client, ai_setup, "I want to book an appointment with Dr. Gina tomorrow")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["response_type"] == "appointment"
    assert len(result["appointment_options"]) > 0
    assert result["appointment_options"][0]["doctor_name"] == "Dr. Gina Tor"
    assert "08:00" in result["summary"] or "08:30" in result["summary"]


async def test_langgraph_upcoming_schedule_does_not_reuse_old_date(
    client: AsyncClient, ai_setup
) -> None:
    """A broad future schedule request searches dates instead of reusing stale date context."""
    first = await ask(client, ai_setup, "I want to book an appointment with Dr. Gina tomorrow")
    assert first.status_code == 201

    res = await ask(client, ai_setup, "Show me the future doctor schedule")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["recommended_doctor_ids"] == [ai_setup["gp"].id]
    assert "upcoming available appointment times" in result["summary"].lower()
    assert result["appointment_options"]


async def test_langgraph_booking_multi_turn_flow(
    client: AsyncClient, ai_setup, session_factory
) -> None:
    """Multi-turn conversation where LangGraph gathers doctor, date, and completes the booking."""
    # Turn 1: Name doctor
    res1 = await ask(client, ai_setup, "I would like to see Dr. Gina")
    assert res1.status_code == 201

    # Turn 2: Provide date
    res2 = await ask(client, ai_setup, "Tomorrow")
    assert res2.status_code == 201
    result2 = res2.json()["assistant_message"]["result"]
    assert len(result2["appointment_options"]) > 0

    # Turn 3: Authorize and pick time slot
    res3 = await ask(client, ai_setup, "Book at 08:00")
    assert res3.status_code == 201
    result3 = res3.json()["assistant_message"]["result"]
    assert result3["appointment_confirmation"] is not None
    assert result3["appointment_confirmation"]["doctor_name"] == "Dr. Gina Tor"
    assert result3["appointment_confirmation"]["status"] == "BOOKED"
    assert "successfully booked" in result3["summary"].lower()

    # Verify appointment persisted in database
    async with session_factory() as db:
        appts = list(await db.scalars(select(Appointment).where(Appointment.doctor_id == ai_setup["gp"].id)))
        assert len(appts) == 1
        assert appts[0].status == AppointmentStatus.BOOKED


async def test_langgraph_booking_all_in_one_turn(
    client: AsyncClient, ai_setup, session_factory
) -> None:
    """Single message with doctor, date, and slot time completes booking automatically."""
    res = await ask(client, ai_setup, "Book an appointment with Dr. Carter tomorrow at 08:30")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["appointment_confirmation"] is not None
    assert result["appointment_confirmation"]["doctor_name"] == "Dr. Carter Tor"
    assert result["appointment_confirmation"]["status"] == "BOOKED"

    # Verify appointment persisted in database
    async with session_factory() as db:
        appts = list(
            await db.scalars(select(Appointment).where(Appointment.doctor_id == ai_setup["cardiologist"].id))
        )
        assert len(appts) == 1
        assert appts[0].status == AppointmentStatus.BOOKED


async def test_langgraph_booking_emergency_symptoms_refuses_routine_booking(
    client: AsyncClient, ai_setup, session_factory
) -> None:
    """When user describes emergency red flags, LangGraph refuses routine booking and directs to emergency care."""
    res = await ask(
        client, ai_setup, "I have severe chest pain and difficulty breathing, please book an appointment with Dr. Carter tomorrow at 08:00"
    )
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["urgency"] == "emergency"
    assert result["emergency_message"] is not None
    assert result["appointment_confirmation"] is None

    # No appointment was booked in DB
    async with session_factory() as db:
        appts = list(
            await db.scalars(select(Appointment).where(Appointment.doctor_id == ai_setup["cardiologist"].id))
        )
        assert len(appts) == 0


async def test_langgraph_doctor_directory_listing(client: AsyncClient, ai_setup) -> None:
    """When user asks to see doctors, LangGraph lists active doctors from the hospital directory."""
    res = await ask(client, ai_setup, "Show all doctors")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert "doctors currently listed" in result["summary"].lower()
    assert len(result["doctor_directory"]) >= 2


async def test_langgraph_handles_misspelled_doctor_list(client: AsyncClient, ai_setup) -> None:
    res = await ask(client, ai_setup, "I need the docter list")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert "Dr. Carter Tor" in result["summary"]
    assert "Dr. Gina Tor" in result["summary"]


async def test_langgraph_doctor_list_includes_live_slots_when_requested(
    client: AsyncClient, ai_setup
) -> None:
    res = await ask(client, ai_setup, "I need docters name and docters available time and slot")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["response_type"] == "appointment"
    assert result["appointment_options"]
    assert "Dr. Carter Tor" in result["summary"] or "Dr. Gina Tor" in result["summary"]


async def test_langgraph_specialty_request_shows_doctors_without_reusing_old_date(
    client: AsyncClient, ai_setup
) -> None:
    first = await ask(client, ai_setup, "Book an appointment with Dr. Carter tomorrow")
    assert first.status_code == 201

    res = await ask(client, ai_setup, "I need to book General Medicine")
    assert res.status_code == 201
    result = res.json()["assistant_message"]["result"]
    assert result["appointment_options"]
    assert {option["doctor_id"] for option in result["appointment_options"]} == {
        ai_setup["gp"].id
    }
    assert "available general medicine doctors" in result["summary"].lower()


async def test_langgraph_upcoming_appointment_question_uses_patient_records(
    client: AsyncClient, ai_setup
) -> None:
    res = await ask(client, ai_setup, "How can I view my upcoming appointments?")
    assert res.status_code == 201
    summary = res.json()["assistant_message"]["result"]["summary"].lower()
    assert "no upcoming appointments" in summary


async def test_langgraph_cancel_request_finds_appointment_and_gives_targeted_steps(
    client: AsyncClient, ai_setup
) -> None:
    created = await client.post(
        f"{API}/appointments",
        json={"doctor_id": ai_setup["gp"].id, "starts_at": slot_start(days_ahead=2).isoformat()},
        headers=ai_setup["headers"],
    )
    assert created.status_code == 201

    res = await ask(client, ai_setup, "I need to delete my upcomming upointmnet")
    assert res.status_code == 201
    summary = res.json()["assistant_message"]["result"]["summary"]
    assert "Dr. Gina Tor" in summary
    assert "choose Cancel" in summary


async def test_langgraph_prescription_question_uses_patient_records(
    client: AsyncClient, ai_setup
) -> None:
    res = await ask(client, ai_setup, "What prescriptions are currently in my account?")
    assert res.status_code == 201
    summary = res.json()["assistant_message"]["result"]["summary"].lower()
    assert "no doctor-issued prescriptions" in summary


async def test_booking_followups_keep_future_slots_and_never_guess_a_slot(
    client: AsyncClient, ai_setup
) -> None:
    first = await ask(
        client,
        ai_setup,
        "I need a genaral checkup; I need to book an appointment",
    )
    assert first.status_code == 201
    first_result = first.json()["assistant_message"]["result"]
    assert first_result["appointment_options"]
    assert {option["doctor_id"] for option in first_result["appointment_options"]} == {
        ai_setup["gp"].id
    }

    future = await ask(client, ai_setup, "Not today, I need a future appointment")
    assert future.status_code == 201
    future_result = future.json()["assistant_message"]["result"]
    assert future_result["appointment_options"]
    assert "upcoming available appointment times" in future_result["summary"].lower()

    specialty = await ask(client, ai_setup, "General Medicine")
    assert specialty.status_code == 201
    assert specialty.json()["assistant_message"]["result"]["appointment_options"]

    for reply in ("okay", "okay proceed", "book the slot"):
        response = await ask(client, ai_setup, reply)
        assert response.status_code == 201
        result = response.json()["assistant_message"]["result"]
        assert result["appointment_options"]
        assert result["appointment_confirmation"] is None
