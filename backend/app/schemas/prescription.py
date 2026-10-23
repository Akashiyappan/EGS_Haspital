from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class PrescriptionItemBase(BaseModel):
    medicine_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    dosage: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    frequency: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    timing: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    duration_days: Annotated[int, Field(ge=1, le=365)]
    instructions: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class PrescriptionItemCreate(PrescriptionItemBase):
    pass


class PrescriptionItemRead(PrescriptionItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int


class PrescriptionDoctorRead(BaseModel):
    id: int
    user_id: int
    full_name: str
    avatar_url: str | None = None
    qualification: str | None = None
    specializations: list[str] = Field(default_factory=list)


class PrescriptionPatientRead(BaseModel):
    id: int
    user_id: int
    full_name: str
    email: str
    phone: str | None = None
    avatar_url: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None


class PrescriptionCreate(BaseModel):
    patient_id: int
    appointment_id: int | None = None
    diagnosis: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)]
    notes: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=3000)] = None
    advice: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=3000)] = None
    follow_up_date: date | None = None
    items: list[PrescriptionItemCreate] = Field(min_length=1)


class PrescriptionUpdate(BaseModel):
    diagnosis: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=2, max_length=500)] = None
    notes: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=3000)] = None
    advice: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=3000)] = None
    follow_up_date: date | None = None
    items: list[PrescriptionItemCreate] | None = None


class PrescriptionRead(BaseModel):
    id: int
    appointment_id: int | None
    doctor_id: int
    patient_id: int
    diagnosis: str
    notes: str | None
    advice: str | None
    follow_up_date: date | None
    created_at: datetime
    updated_at: datetime
    doctor: PrescriptionDoctorRead
    patient: PrescriptionPatientRead
    items: list[PrescriptionItemRead]
    is_active: bool
    days_remaining: int


class PrescriptionRequestCreate(BaseModel):
    doctor_id: int
    appointment_id: int | None = None
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1000)]


class PrescriptionRequestRead(BaseModel):
    id: int
    patient_id: int
    doctor_id: int
    appointment_id: int | None
    reason: str
    status: str
    created_at: datetime
    patient_name: str
    doctor_name: str
