from datetime import datetime

from pydantic import BaseModel


class VisitRecordRead(BaseModel):
    appointment_id: int
    date: datetime
    doctor_name: str
    specializations: list[str]
    reason: str | None
    clinical_notes: str | None

