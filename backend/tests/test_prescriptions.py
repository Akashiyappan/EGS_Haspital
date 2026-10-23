from datetime import date, timedelta

from httpx import AsyncClient

from tests.helpers import (
    API,
    iso,
    login,
    make_doctor,
    make_patient,
    slot_start,
)


async def test_prescription_lifecycle(client: AsyncClient, session_factory) -> None:
    _, doctor = await make_doctor(session_factory, "doc_rx@example.com")
    _, patient_id = await make_patient(session_factory, "pat_rx@example.com")
    doctor_h = await login(client, "doc_rx@example.com", portal="staff")
    patient_h = await login(client, "pat_rx@example.com")

    # 1. Book an appointment
    start_dt = slot_start()
    book_res = await client.post(
        f"{API}/appointments",
        json={"doctor_id": doctor.id, "starts_at": iso(start_dt), "reason": "Persistent fever and cough"},
        headers=patient_h,
    )
    assert book_res.status_code == 201
    appt_id = book_res.json()["id"]

    # 2. Patient cannot issue a prescription
    forbidden_res = await client.post(
        f"{API}/prescriptions",
        json={
            "patient_id": patient_id,
            "appointment_id": appt_id,
            "diagnosis": "Viral Bronchitis",
            "items": [
                {
                    "medicine_name": "Paracetamol 500mg",
                    "dosage": "1 tablet",
                    "frequency": "1-0-1",
                    "timing": "After food",
                    "duration_days": 5,
                }
            ],
        },
        headers=patient_h,
    )
    assert forbidden_res.status_code == 403

    # 3. Doctor issues prescription
    follow_up = (date.today() + timedelta(days=7)).isoformat()
    create_res = await client.post(
        f"{API}/prescriptions",
        json={
            "patient_id": patient_id,
            "appointment_id": appt_id,
            "diagnosis": "Acute Upper Respiratory Tract Infection",
            "notes": "Patient has mild wheezing, clear lungs.",
            "advice": "Drink warm water, take rest, avoid cold drinks.",
            "follow_up_date": follow_up,
            "items": [
                {
                    "medicine_name": "Amoxicillin 500mg",
                    "dosage": "1 capsule",
                    "frequency": "1-1-1 (Thrice daily)",
                    "timing": "After food",
                    "duration_days": 5,
                    "instructions": "Complete the full 5-day course",
                },
                {
                    "medicine_name": "Cetirizine 10mg",
                    "dosage": "1 tablet",
                    "frequency": "0-0-1 (Bedtime)",
                    "timing": "After food",
                    "duration_days": 7,
                    "instructions": "May cause drowsiness",
                },
            ],
        },
        headers=doctor_h,
    )
    assert create_res.status_code == 201
    rx_data = create_res.json()
    assert rx_data["diagnosis"] == "Acute Upper Respiratory Tract Infection"
    assert rx_data["is_active"] is True
    assert len(rx_data["items"]) == 2
    assert rx_data["doctor"]["full_name"] is not None
    rx_id = rx_data["id"]

    # 4. Patient reads prescription
    pat_get_res = await client.get(f"{API}/prescriptions/{rx_id}", headers=patient_h)
    assert pat_get_res.status_code == 200
    assert pat_get_res.json()["id"] == rx_id

    # 5. Get by appointment
    appt_rx_res = await client.get(f"{API}/prescriptions/appointment/{appt_id}", headers=patient_h)
    assert appt_rx_res.status_code == 200
    assert appt_rx_res.json()["id"] == rx_id

    # 6. Patient list prescriptions
    pat_list_res = await client.get(f"{API}/prescriptions", headers=patient_h)
    assert pat_list_res.status_code == 200
    items = pat_list_res.json()
    assert len(items) == 1
    assert items[0]["id"] == rx_id

    # 7. Doctor updates prescription
    update_res = await client.put(
        f"{API}/prescriptions/{rx_id}",
        json={
            "diagnosis": "Acute Bronchitis (Recovering)",
            "advice": "Continue breathing exercises",
        },
        headers=doctor_h,
    )
    assert update_res.status_code == 200
    assert update_res.json()["diagnosis"] == "Acute Bronchitis (Recovering)"
    assert update_res.json()["advice"] == "Continue breathing exercises"

    # 8. Patient checks notification
    notif_res = await client.get(f"{API}/notifications", headers=patient_h)
    assert notif_res.status_code == 200
    notifs = notif_res.json()["items"]
    rx_notif = next((n for n in notifs if n["type"] == "PRESCRIPTION_ISSUED"), None)
    assert rx_notif is not None
    assert "prescription" in rx_notif["title"].lower()

    # 9. Doctor deletes prescription
    del_res = await client.delete(f"{API}/prescriptions/{rx_id}", headers=doctor_h)
    assert del_res.status_code == 204

    # Now 404
    after_del = await client.get(f"{API}/prescriptions/{rx_id}", headers=patient_h)
    assert after_del.status_code == 404
