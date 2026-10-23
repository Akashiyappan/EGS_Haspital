import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenError, NotFoundError
from app.models import (
    Appointment,
    Doctor,
    NotificationType,
    Patient,
    Prescription,
    PrescriptionItem,
    PrescriptionRequest,
    Role,
    PrescriptionRequestStatus,
    User,
)
from app.schemas.prescription import (
    PrescriptionCreate,
    PrescriptionDoctorRead,
    PrescriptionItemRead,
    PrescriptionPatientRead,
    PrescriptionRead,
    PrescriptionUpdate,
    PrescriptionRequestCreate,
    PrescriptionRequestRead,
)
from app.services.notification_service import NotificationPayload, Notifier

logger = logging.getLogger(__name__)


async def create_prescription_request(db: AsyncSession, patient_user: User, payload: PrescriptionRequestCreate) -> PrescriptionRequestRead:
    patient = await db.scalar(select(Patient).where(Patient.user_id == patient_user.id))
    doctor = await db.scalar(select(Doctor).where(Doctor.id == payload.doctor_id))
    if patient is None or doctor is None:
        raise NotFoundError("Patient or doctor not found")
    if payload.appointment_id is not None:
        appointment = await db.get(Appointment, payload.appointment_id)
        if appointment is None or appointment.patient_id != patient.id or appointment.doctor_id != doctor.id:
            raise NotFoundError("Matching appointment not found")
    request = PrescriptionRequest(patient_id=patient.id, doctor_id=doctor.id, appointment_id=payload.appointment_id, reason=payload.reason, status=PrescriptionRequestStatus.PENDING.value)
    db.add(request)
    await db.commit()
    await db.refresh(request)
    notifier = Notifier(db)
    await notifier.add(
        doctor.user_id,
        NotificationPayload(
            type=NotificationType.PRESCRIPTION_REQUESTED,
            title="Prescription request",
            body=f"{patient.user.full_name} requested a prescription review.",
            data={"prescription_request_id": request.id, "patient_id": patient.id},
            dedupe_key=f"prescription_request_{request.id}",
        ),
    )
    await db.commit()
    await notifier.dispatch()
    return await _request_read(db, request)


async def _request_read(db: AsyncSession, request: PrescriptionRequest) -> PrescriptionRequestRead:
    patient = await db.scalar(select(Patient).where(Patient.id == request.patient_id).options(selectinload(Patient.user)))
    doctor = await db.scalar(select(Doctor).where(Doctor.id == request.doctor_id).options(selectinload(Doctor.user)))
    return PrescriptionRequestRead(id=request.id, patient_id=request.patient_id, doctor_id=request.doctor_id,
        appointment_id=request.appointment_id, reason=request.reason, status=request.status,
        created_at=request.created_at, patient_name=patient.user.full_name, doctor_name=doctor.user.full_name)


async def list_prescription_requests(db: AsyncSession, user: User) -> list[PrescriptionRequestRead]:
    stmt = select(PrescriptionRequest)
    if user.role == Role.PATIENT:
        patient = await db.scalar(select(Patient).where(Patient.user_id == user.id))
        if patient is None: return []
        stmt = stmt.where(PrescriptionRequest.patient_id == patient.id)
    elif user.role == Role.DOCTOR:
        doctor = await db.scalar(select(Doctor).where(Doctor.user_id == user.id))
        if doctor is None: return []
        stmt = stmt.where(PrescriptionRequest.doctor_id == doctor.id)
    requests = (await db.scalars(stmt.order_by(PrescriptionRequest.created_at.desc()))).all()
    return [await _request_read(db, request) for request in requests]


async def complete_prescription_request(db: AsyncSession, user: User, request_id: int) -> None:
    doctor = await db.scalar(select(Doctor).where(Doctor.user_id == user.id))
    request = await db.get(PrescriptionRequest, request_id)
    if doctor is None or request is None or request.doctor_id != doctor.id:
        raise NotFoundError("Prescription request not found")
    request.status = PrescriptionRequestStatus.APPROVED.value
    await db.commit()


def _with_relations(stmt: Select[tuple[Prescription]]) -> Select[tuple[Prescription]]:
    return stmt.options(
        selectinload(Prescription.doctor).selectinload(Doctor.user),
        selectinload(Prescription.doctor).selectinload(Doctor.specializations),
        selectinload(Prescription.patient).selectinload(Patient.user),
        selectinload(Prescription.items),
        selectinload(Prescription.appointment),
    )


def _to_read(prescription: Prescription) -> PrescriptionRead:
    doctor_user = prescription.doctor.user
    patient_user = prescription.patient.user

    doctor_read = PrescriptionDoctorRead(
        id=prescription.doctor.id,
        user_id=doctor_user.id,
        full_name=doctor_user.full_name,
        avatar_url=doctor_user.avatar_url,
        qualification=prescription.doctor.qualification,
        specializations=[s.name for s in prescription.doctor.specializations],
    )

    patient_read = PrescriptionPatientRead(
        id=prescription.patient.id,
        user_id=patient_user.id,
        full_name=patient_user.full_name,
        email=patient_user.email,
        phone=patient_user.phone,
        avatar_url=patient_user.avatar_url,
        date_of_birth=prescription.patient.date_of_birth,
        gender=prescription.patient.gender,
    )

    items_read = [
        PrescriptionItemRead(
            id=item.id,
            medicine_name=item.medicine_name,
            dosage=item.dosage,
            frequency=item.frequency,
            timing=item.timing,
            duration_days=item.duration_days,
            instructions=item.instructions,
        )
        for item in prescription.items
    ]

    now_utc = datetime.now(UTC)
    max_duration = max((item.duration_days for item in prescription.items), default=0)
    created_date = prescription.created_at.date() if prescription.created_at else now_utc.date()
    expiry_date = created_date + timedelta(days=max_duration)
    today = now_utc.date()
    is_active = today <= expiry_date
    days_remaining = max(0, (expiry_date - today).days) if is_active else 0

    return PrescriptionRead(
        id=prescription.id,
        appointment_id=prescription.appointment_id,
        doctor_id=prescription.doctor_id,
        patient_id=prescription.patient_id,
        diagnosis=prescription.diagnosis,
        notes=prescription.notes,
        advice=prescription.advice,
        follow_up_date=prescription.follow_up_date,
        created_at=prescription.created_at,
        updated_at=prescription.updated_at,
        doctor=doctor_read,
        patient=patient_read,
        items=items_read,
        is_active=is_active,
        days_remaining=days_remaining,
    )


async def create_prescription(
    db: AsyncSession,
    doctor_user: User,
    payload: PrescriptionCreate,
) -> PrescriptionRead:
    doctor = await db.scalar(
        select(Doctor).where(Doctor.user_id == doctor_user.id)
    )
    if doctor is None:
        raise ForbiddenError("Only registered doctors can issue prescriptions")

    patient = await db.get(Patient, payload.patient_id)
    if patient is None:
        raise NotFoundError("Patient not found")

    if payload.appointment_id is not None:
        appointment = await db.get(Appointment, payload.appointment_id)
        if appointment is None:
            raise NotFoundError("Appointment not found")
        if appointment.doctor_id != doctor.id:
            raise ForbiddenError("You may only issue prescriptions for your own appointments")
        if appointment.patient_id != patient.id:
            raise ForbiddenError("Appointment does not match selected patient")

    prescription = Prescription(
        appointment_id=payload.appointment_id,
        doctor_id=doctor.id,
        patient_id=patient.id,
        diagnosis=payload.diagnosis,
        notes=payload.notes,
        advice=payload.advice,
        follow_up_date=payload.follow_up_date,
    )
    db.add(prescription)
    await db.flush()

    for item_data in payload.items:
        item = PrescriptionItem(
            prescription_id=prescription.id,
            medicine_name=item_data.medicine_name,
            dosage=item_data.dosage,
            frequency=item_data.frequency,
            timing=item_data.timing,
            duration_days=item_data.duration_days,
            instructions=item_data.instructions,
        )
        db.add(item)

    await db.flush()

    # Re-fetch with all relations loaded
    loaded = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.id == prescription.id))
    )
    if loaded is None:
        raise NotFoundError("Prescription not found")

    # Notification to patient
    notifier = Notifier(db)
    await notifier.add(
        patient.user_id,
        NotificationPayload(
            type=NotificationType.PRESCRIPTION_ISSUED,
            title="New Prescription Issued",
            body=f"Dr. {doctor_user.full_name} has issued an official prescription for '{payload.diagnosis}'.",
            data={
                "prescription_id": prescription.id,
                "appointment_id": payload.appointment_id,
                "doctor_name": doctor_user.full_name,
            },
            dedupe_key=f"prescription_{prescription.id}",
        ),
    )

    await db.commit()
    await notifier.dispatch()

    return _to_read(loaded)


async def get_prescription(
    db: AsyncSession,
    current_user: User,
    prescription_id: int,
) -> PrescriptionRead:
    prescription = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.id == prescription_id))
    )
    if prescription is None:
        raise NotFoundError("Prescription not found")

    if current_user.role == Role.PATIENT and prescription.patient.user_id != current_user.id:
        raise NotFoundError("Prescription not found")

    return _to_read(prescription)


async def get_appointment_prescription(
    db: AsyncSession,
    current_user: User,
    appointment_id: int,
) -> PrescriptionRead | None:
    prescription = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.appointment_id == appointment_id))
    )
    if prescription is None:
        return None

    if current_user.role == Role.PATIENT and prescription.patient.user_id != current_user.id:
        return None

    return _to_read(prescription)


async def list_prescriptions(
    db: AsyncSession,
    current_user: User,
    patient_id: int | None = None,
    doctor_id: int | None = None,
    active_only: bool = False,
) -> list[PrescriptionRead]:
    stmt = _with_relations(select(Prescription))

    if current_user.role == Role.PATIENT:
        patient = await db.scalar(select(Patient).where(Patient.user_id == current_user.id))
        if patient is None:
            return []
        stmt = stmt.where(Prescription.patient_id == patient.id)
    elif current_user.role == Role.DOCTOR:
        doctor = await db.scalar(select(Doctor).where(Doctor.user_id == current_user.id))
        if doctor is None:
            return []
        if patient_id:
            stmt = stmt.where(Prescription.patient_id == patient_id)
        else:
            stmt = stmt.where(Prescription.doctor_id == doctor.id)
    else:  # ADMIN
        if patient_id:
            stmt = stmt.where(Prescription.patient_id == patient_id)
        if doctor_id:
            stmt = stmt.where(Prescription.doctor_id == doctor_id)

    stmt = stmt.order_by(Prescription.created_at.desc(), Prescription.id.desc())
    results = await db.scalars(stmt)
    prescriptions = [_to_read(p) for p in results]

    if active_only:
        prescriptions = [p for p in prescriptions if p.is_active]

    return prescriptions


async def update_prescription(
    db: AsyncSession,
    doctor_user: User,
    prescription_id: int,
    payload: PrescriptionUpdate,
) -> PrescriptionRead:
    prescription = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.id == prescription_id))
    )
    if prescription is None:
        raise NotFoundError("Prescription not found")

    if prescription.doctor.user_id != doctor_user.id:
        raise ForbiddenError("Only the prescribing doctor may update this prescription")

    if payload.diagnosis is not None:
        prescription.diagnosis = payload.diagnosis
    if payload.notes is not None:
        prescription.notes = payload.notes
    if payload.advice is not None:
        prescription.advice = payload.advice
    if payload.follow_up_date is not None:
        prescription.follow_up_date = payload.follow_up_date

    if payload.items is not None:
        # Replace items
        for existing_item in list(prescription.items):
            await db.delete(existing_item)
        await db.flush()

        for item_data in payload.items:
            new_item = PrescriptionItem(
                prescription_id=prescription.id,
                medicine_name=item_data.medicine_name,
                dosage=item_data.dosage,
                frequency=item_data.frequency,
                timing=item_data.timing,
                duration_days=item_data.duration_days,
                instructions=item_data.instructions,
            )
            db.add(new_item)

    await db.commit()

    reloaded = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.id == prescription_id))
    )
    if reloaded is None:
        raise NotFoundError("Prescription not found")
    return _to_read(reloaded)


async def delete_prescription(
    db: AsyncSession,
    doctor_user: User,
    prescription_id: int,
) -> None:
    prescription = await db.scalar(
        _with_relations(select(Prescription).where(Prescription.id == prescription_id))
    )
    if prescription is None:
        raise NotFoundError("Prescription not found")

    if prescription.doctor.user_id != doctor_user.id and doctor_user.role != Role.ADMIN:
        raise ForbiddenError("You may only delete your own prescriptions")

    await db.delete(prescription)
    await db.commit()
