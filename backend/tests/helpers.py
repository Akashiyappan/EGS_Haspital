"""Test data builders. Accounts are created directly in the database (fast);
the API flows themselves are covered by the dedicated tests."""

from datetime import UTC, datetime, time, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.security import hash_password
from app.core.timeutils import clinic_today, local_to_utc
from app.models import (
    Appointment,
    AppointmentStatus,
    Doctor,
    DoctorSchedule,
    Patient,
    Role,
    Specialization,
    User,
)

API = "/api/v1"
PASSWORD = "Passw0rd!"

Sessions = async_sessionmaker[AsyncSession]


async def make_user(
    sessions: Sessions,
    role: Role,
    email: str,
    first_name: str = "Test",
    *,
    must_change_password: bool = False,
    is_active: bool = True,
) -> User:
    async with sessions() as db:
        user = User(
            email=email,
            first_name=first_name,
            last_name="User",
            role=role,
            hashed_password=hash_password(PASSWORD),
            must_change_password=must_change_password,
            is_active=is_active,
        )
        db.add(user)
        await db.flush()
        if role == Role.PATIENT:
            db.add(Patient(user_id=user.id))
        await db.commit()
        return user


async def make_admin(sessions: Sessions, email: str = "admin@example.com") -> User:
    return await make_user(sessions, Role.ADMIN, email, "Ada")


async def make_patient(sessions: Sessions, email: str = "patient@example.com") -> tuple[User, int]:
    user = await make_user(sessions, Role.PATIENT, email, "Pat")
    async with sessions() as db:
        from sqlalchemy import select

        patient_id = await db.scalar(select(Patient.id).where(Patient.user_id == user.id))
    assert patient_id is not None
    return user, patient_id


async def make_specialization(sessions: Sessions, name: str = "Cardiology") -> Specialization:
    async with sessions() as db:
        spec = Specialization(name=name, description=f"{name} description")
        db.add(spec)
        await db.commit()
        return spec


async def make_doctor(
    sessions: Sessions,
    email: str = "doctor@example.com",
    *,
    specialization: str = "Cardiology",
    with_schedule: bool = True,
    first_name: str = "Doc",
) -> tuple[User, Doctor]:
    async with sessions() as db:
        from sqlalchemy import select

        spec = await db.scalar(select(Specialization).where(Specialization.name == specialization))
        if spec is None:
            spec = Specialization(name=specialization)
            db.add(spec)
        user = User(
            email=email,
            first_name=first_name,
            last_name="Tor",
            role=Role.DOCTOR,
            hashed_password=hash_password(PASSWORD),
        )
        doctor = Doctor(user=user, qualification="MBBS", experience_years=5, specializations=[spec])
        db.add(doctor)
        await db.flush()
        if with_schedule:
            for weekday in range(7):
                db.add(
                    DoctorSchedule(
                        doctor_id=doctor.id,
                        weekday=weekday,
                        start_time=time(8, 0),
                        end_time=time(10, 0),
                        slot_minutes=settings.APPOINTMENT_DURATION_MINUTES,
                    )
                )
        await db.commit()
        return user, doctor


async def login(
    client: AsyncClient, email: str, portal: str = "patient", password: str = PASSWORD
) -> dict[str, str]:
    res = await client.post(
        f"{API}/auth/login", json={"email": email, "password": password, "portal": portal}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def booking_day(days_ahead: int = 2):  # type: ignore[no-untyped-def]
    return clinic_today() + timedelta(days=days_ahead)


def slot_start(days_ahead: int = 2, hour: int = 8, minute: int = 0) -> datetime:
    start = local_to_utc(booking_day(days_ahead), time(hour, minute), settings.clinic_tz)
    assert start is not None
    return start


def iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


async def make_appointment(
    sessions: Sessions,
    doctor_id: int,
    patient_id: int,
    starts_at: datetime,
    status: AppointmentStatus = AppointmentStatus.BOOKED,
) -> int:
    """Insert directly (e.g. in the past) to test status transitions."""
    async with sessions() as db:
        appointment = Appointment(
            doctor_id=doctor_id,
            patient_id=patient_id,
            starts_at=starts_at,
            ends_at=starts_at + timedelta(minutes=30),
            status=status,
        )
        db.add(appointment)
        await db.commit()
        return appointment.id
