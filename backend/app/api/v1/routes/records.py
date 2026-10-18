from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentPatient, DbSession
from app.models import Appointment, AppointmentStatus, Doctor
from app.schemas.record import VisitRecordRead

router = APIRouter(prefix="/records", tags=["patient records"])


@router.get("/visits", response_model=list[VisitRecordRead], summary="Patient visit history")
async def visit_history(patient: CurrentPatient, db: DbSession) -> list[VisitRecordRead]:
    """Return completed visits and clinician notes for the signed-in patient only."""
    rows = await db.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == patient.id,
            Appointment.status == AppointmentStatus.COMPLETED,
        )
        .options(
            selectinload(Appointment.doctor).selectinload(Doctor.specializations),
            selectinload(Appointment.doctor).selectinload(Doctor.user),
        )
        .order_by(Appointment.starts_at.desc(), Appointment.id.desc())
    )
    return [
        VisitRecordRead(
            appointment_id=visit.id,
            date=visit.starts_at,
            doctor_name=visit.doctor.user.full_name,
            specializations=[specialization.name for specialization in visit.doctor.specializations],
            reason=visit.reason,
            clinical_notes=visit.doctor_notes,
        )
        for visit in rows
    ]
