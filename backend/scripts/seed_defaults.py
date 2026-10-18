"""Seed default users: 1 Admin, 1 Doctor, and 1 Patient (idempotent).

Usage:
    python -m scripts.seed_defaults

Default credentials created:
    - Admin:   admin@hospital.com   / AdminPassword123   (Portal: Staff)
    - Doctor:  doctor@hospital.com  / DoctorPassword123  (Portal: Staff)
    - Patient: patient@hospital.com / PatientPassword123 (Portal: Patient)
"""

import asyncio
import os
from datetime import date, time

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models import Doctor, DoctorSchedule, Patient, Role, User
from scripts.seed import seed_specializations

# Default user configuration
ADMIN_EMAIL = os.environ.get("DEFAULT_ADMIN_EMAIL", "admin@hospital.com")
ADMIN_PASSWORD = os.environ.get("DEFAULT_ADMIN_PASSWORD", "AdminPassword123")

DOCTOR_EMAIL = os.environ.get("DEFAULT_DOCTOR_EMAIL", "doctor@hospital.com")
DOCTOR_PASSWORD = os.environ.get("DEFAULT_DOCTOR_PASSWORD", "DoctorPassword123")

PATIENT_EMAIL = os.environ.get("DEFAULT_PATIENT_EMAIL", "patient@hospital.com")
PATIENT_PASSWORD = os.environ.get("DEFAULT_PATIENT_PASSWORD", "PatientPassword123")


async def ensure_user(
    db,
    email: str,
    first_name: str,
    last_name: str,
    role: Role,
    password: str,
    phone: str | None = None,
) -> tuple[User, bool]:
    """Get existing user or create a new user. Returns (user, created_flag)."""
    existing = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if existing:
        return existing, False

    user = User(
        email=email.strip().lower(),
        first_name=first_name,
        last_name=last_name,
        role=role,
        hashed_password=hash_password(password),
        phone=phone,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    return user, True


async def seed_defaults() -> None:
    print("=" * 60)
    print("Starting Hospital Database Seeding...")
    print("=" * 60)

    # 1. Seed specializations first
    print("\n[1/4] Seeding medical specializations...")
    specs = await seed_specializations()
    print(f"      Loaded {len(specs)} specializations.")

    async with SessionLocal() as db:
        # 2. Seed Admin
        print("\n[2/4] Seeding Default Admin user...")
        _admin, created_admin = await ensure_user(
            db=db,
            email=ADMIN_EMAIL,
            first_name="Hospital",
            last_name="Administrator",
            role=Role.ADMIN,
            password=ADMIN_PASSWORD,
            phone="+91 9876543210",
        )
        if created_admin:
            print(f"      [CREATED] Admin: {ADMIN_EMAIL}")
        else:
            print(f"      [EXISTS]  Admin: {ADMIN_EMAIL}")

        # 3. Seed Doctor
        print("\n[3/4] Seeding Default Doctor user & profile...")
        doctor_user, _created_doctor_user = await ensure_user(
            db=db,
            email=DOCTOR_EMAIL,
            first_name="Rajesh",
            last_name="Sharma",
            role=Role.DOCTOR,
            password=DOCTOR_PASSWORD,
            phone="+91 9876543211",
        )

        existing_doctor = await db.scalar(
            select(Doctor).where(Doctor.user_id == doctor_user.id)
        )
        if not existing_doctor:
            general_med = specs.get("General Medicine") or next(iter(specs.values()))
            doctor = Doctor(
                user_id=doctor_user.id,
                qualification="MBBS, MD (General Medicine)",
                experience_years=10,
                bio="Dr. Rajesh Sharma is a Senior Consultant in General Medicine with over 10 years of clinical experience.",
                specializations=[general_med],
            )
            db.add(doctor)
            await db.flush()

            # Add weekly working schedule: Mon-Sat, morning & afternoon shifts
            for weekday in range(6):  # 0=Mon, 5=Sat
                for start, end in ((time(9, 0), time(13, 0)), (time(14, 0), time(18, 0))):
                    db.add(
                        DoctorSchedule(
                            doctor_id=doctor.id,
                            weekday=weekday,
                            start_time=start,
                            end_time=end,
                            slot_minutes=settings.APPOINTMENT_DURATION_MINUTES,
                        )
                    )
            print(f"      [CREATED] Doctor profile & schedules for {DOCTOR_EMAIL}")
        else:
            print(f"      [EXISTS]  Doctor profile for {DOCTOR_EMAIL}")

        # 4. Seed Patient
        print("\n[4/4] Seeding Default Patient user & profile...")
        patient_user, _created_patient_user = await ensure_user(
            db=db,
            email=PATIENT_EMAIL,
            first_name="Ramesh",
            last_name="Kumar",
            role=Role.PATIENT,
            password=PATIENT_PASSWORD,
            phone="+91 9876543212",
        )

        existing_patient = await db.scalar(
            select(Patient).where(Patient.user_id == patient_user.id)
        )
        if not existing_patient:
            patient = Patient(
                user_id=patient_user.id,
                date_of_birth=date(1995, 5, 15),
                gender="Male",
                emergency_contact_name="Suresh Kumar",
                emergency_contact_phone="+91 9876543213",
            )
            db.add(patient)
            print(f"      [CREATED] Patient profile for {PATIENT_EMAIL}")
        else:
            print(f"      [EXISTS]  Patient profile for {PATIENT_EMAIL}")

        await db.commit()

    print("\n" + "=" * 60)
    print("Database seeding completed successfully!")
    print("=" * 60)
    print("Default Login Credentials:")
    print("-" * 60)
    print("1. ADMIN (Staff Portal):")
    print(f"   Email:    {ADMIN_EMAIL}")
    print(f"   Password: {ADMIN_PASSWORD}")
    print()
    print("2. DOCTOR (Staff Portal):")
    print(f"   Email:    {DOCTOR_EMAIL}")
    print(f"   Password: {DOCTOR_PASSWORD}")
    print()
    print("3. PATIENT (Patient Portal):")
    print(f"   Email:    {PATIENT_EMAIL}")
    print(f"   Password: {PATIENT_PASSWORD}")
    print("-" * 60)


async def main() -> None:
    try:
        await seed_defaults()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
