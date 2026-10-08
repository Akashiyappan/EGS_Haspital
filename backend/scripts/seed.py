"""Seed reference data (idempotent).

    python -m scripts.seed              # specializations only (safe for production)
    python -m scripts.seed --demo       # + demo admin/doctors/patient with schedules (dev only)

Demo accounts use the password given by SEED_DEMO_PASSWORD (required with --demo).
"""

import asyncio
import os
import sys
from datetime import time

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import Doctor, DoctorSchedule, Patient, Role, Specialization, User

SPECIALIZATIONS = {
    "General Medicine": "First point of care for common illnesses, fever, infections and check-ups.",
    "Cardiology": "Heart and blood vessels: chest pain, palpitations, blood pressure.",
    "Neurology": "Brain and nerves: headaches, seizures, numbness, dizziness.",
    "Dermatology": "Skin, hair and nails: rashes, acne, allergies.",
    "Orthopedics": "Bones, joints and muscles: fractures, back and joint pain.",
    "Pediatrics": "Medical care for infants, children and adolescents.",
    "ENT": "Ear, nose and throat: sinus, hearing, tonsils.",
    "Gynecology": "Women's reproductive health and pregnancy.",
    "Gastroenterology": "Digestive system: stomach pain, acidity, liver.",
    "Pulmonology": "Lungs and breathing: cough, asthma, breathlessness.",
}

DEMO_DOCTORS = [
    ("anita.rao.demo@example.com", "Anita", "Rao", ["General Medicine"], "MBBS, MD", 12),
    ("vikram.shah.demo@example.com", "Vikram", "Shah", ["Cardiology"], "MBBS, DM Cardiology", 15),
    ("meera.iyer.demo@example.com", "Meera", "Iyer", ["Neurology"], "MBBS, DM Neurology", 9),
    ("rahul.nair.demo@example.com", "Rahul", "Nair", ["Pediatrics"], "MBBS, MD Pediatrics", 7),
]


async def seed_specializations() -> dict[str, Specialization]:
    async with SessionLocal() as db:
        existing = {s.name: s for s in await db.scalars(select(Specialization))}
        for name, description in SPECIALIZATIONS.items():
            if name not in existing:
                db.add(Specialization(name=name, description=description))
        await db.commit()
        return {s.name: s for s in await db.scalars(select(Specialization))}


async def seed_demo(password: str) -> None:
    specs = await seed_specializations()
    hashed = hash_password(password)
    async with SessionLocal() as db:

        async def ensure_user(email: str, first: str, last: str, role: Role) -> User | None:
            if await db.scalar(select(User).where(User.email == email)):
                return None
            user = User(
                email=email, first_name=first, last_name=last, role=role, hashed_password=hashed
            )
            db.add(user)
            await db.flush()
            return user

        await ensure_user("admin.demo@example.com", "Clinic", "Admin", Role.ADMIN)
        patient = await ensure_user("patient.demo@example.com", "Priya", "Kumar", Role.PATIENT)
        if patient:
            db.add(Patient(user_id=patient.id))

        for email, first, last, spec_names, qualification, years in DEMO_DOCTORS:
            user = await ensure_user(email, first, last, Role.DOCTOR)
            if user is None:
                continue
            doctor = Doctor(
                user_id=user.id,
                qualification=qualification,
                experience_years=years,
                bio=f"Dr. {first} {last} has {years} years of clinical experience.",
                specializations=[specs[n] for n in spec_names],
            )
            db.add(doctor)
            await db.flush()
            for weekday in range(6):  # Mon-Sat: morning and afternoon shifts
                for start, end in ((time(8, 0), time(10, 0)), (time(14, 0), time(16, 0))):
                    db.add(
                        DoctorSchedule(
                            doctor_id=doctor.id,
                            weekday=weekday,
                            start_time=start,
                            end_time=end,
                            slot_minutes=settings.APPOINTMENT_DURATION_MINUTES,
                        )
                    )
        await db.commit()


async def main() -> None:
    if "--demo" in sys.argv:
        if settings.is_production:
            sys.exit("Refusing to create demo accounts in production")
        password = os.environ.get("SEED_DEMO_PASSWORD")
        if not password:
            sys.exit("Set SEED_DEMO_PASSWORD to the password for demo accounts")
        await seed_demo(password)
        print("Seeded specializations and demo accounts (*.demo@example.com)")
    else:
        await seed_specializations()
        print("Seeded specializations")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
