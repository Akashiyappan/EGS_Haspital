from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import CurrentDoctor, CurrentUser, DbSession
from app.schemas.common import error_responses
from app.schemas.prescription import (
    PrescriptionRequestCreate,
    PrescriptionRequestRead,
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionUpdate,
)
from app.services import prescription_service

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.post("/requests", response_model=PrescriptionRequestRead, status_code=status.HTTP_201_CREATED)
async def create_request(body: PrescriptionRequestCreate, user: CurrentUser, db: DbSession) -> PrescriptionRequestRead:
    if user.role.value != "PATIENT":
        from app.core.exceptions import ForbiddenError
        raise ForbiddenError("Only patients can request prescriptions")
    return await prescription_service.create_prescription_request(db, user, body)


@router.get("/requests", response_model=list[PrescriptionRequestRead])
async def list_requests(user: CurrentUser, db: DbSession) -> list[PrescriptionRequestRead]:
    return await prescription_service.list_prescription_requests(db, user)


@router.post("/requests/{request_id}/fulfill", status_code=status.HTTP_204_NO_CONTENT)
async def fulfill_request(request_id: int, doctor: CurrentDoctor, db: DbSession) -> Response:
    await prescription_service.complete_prescription_request(db, doctor.user, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "",
    response_model=PrescriptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Issue a new e-prescription",
    description="Doctors can issue structured e-prescriptions with diagnosis, medicines, dosages, and instructions.",
    responses=error_responses(400, 401, 403, 404, 422),
)
async def create_prescription(
    body: PrescriptionCreate,
    doctor: CurrentDoctor,
    db: DbSession,
) -> PrescriptionRead:
    return await prescription_service.create_prescription(db, doctor.user, body)


@router.get(
    "",
    response_model=list[PrescriptionRead],
    summary="List prescriptions",
    description="Patients see their prescriptions; doctors see prescriptions they have issued; admins can query all.",
    responses=error_responses(401, 403),
)
async def list_prescriptions(
    user: CurrentUser,
    db: DbSession,
    patient_id: Annotated[int | None, Query(description="Filter by patient ID (doctors/admins)")] = None,
    doctor_id: Annotated[int | None, Query(description="Filter by doctor ID (admins)")] = None,
    active_only: Annotated[bool, Query(description="Return only active medications ongoing today")] = False,
) -> list[PrescriptionRead]:
    return await prescription_service.list_prescriptions(
        db,
        user,
        patient_id=patient_id,
        doctor_id=doctor_id,
        active_only=active_only,
    )


@router.get(
    "/appointment/{appointment_id}",
    response_model=PrescriptionRead | None,
    summary="Get prescription for appointment",
    description="Fetch prescription linked to a specific appointment ID.",
    responses=error_responses(401, 403),
)
async def get_appointment_prescription(
    appointment_id: int,
    user: CurrentUser,
    db: DbSession,
) -> PrescriptionRead | None:
    return await prescription_service.get_appointment_prescription(db, user, appointment_id)


@router.get(
    "/{id}",
    response_model=PrescriptionRead,
    summary="Get prescription details",
    description="Retrieve a single prescription by ID with full item details and doctor/patient information.",
    responses=error_responses(401, 403, 404),
)
async def get_prescription(
    id: int,
    user: CurrentUser,
    db: DbSession,
) -> PrescriptionRead:
    return await prescription_service.get_prescription(db, user, id)


@router.put(
    "/{id}",
    response_model=PrescriptionRead,
    summary="Update prescription",
    description="Allows the prescribing doctor to modify diagnosis, medications, or instructions.",
    responses=error_responses(401, 403, 404, 422),
)
async def update_prescription(
    id: int,
    body: PrescriptionUpdate,
    doctor: CurrentDoctor,
    db: DbSession,
) -> PrescriptionRead:
    return await prescription_service.update_prescription(db, doctor.user, id, body)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete prescription",
    description="Prescribing doctor or admin can delete an issued prescription.",
    responses=error_responses(401, 403, 404),
)
async def delete_prescription(
    id: int,
    doctor: CurrentDoctor,
    db: DbSession,
) -> None:
    await prescription_service.delete_prescription(db, doctor.user, id)
