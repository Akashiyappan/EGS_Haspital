from datetime import datetime
from typing import Any

from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: int
    type: str
    title: str
    body: str
    data: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class AuditLogRead(ORMModel):
    id: int
    actor_id: int | None
    action: str
    entity_type: str | None
    entity_id: str | None
    details: dict[str, Any]
    ip_address: str | None
    request_id: str | None
    created_at: datetime


class AdminStats(ORMModel):
    doctors_active: int
    doctors_inactive: int
    patients: int
    appointments_today: int
    appointments_upcoming: int
    appointments_by_status: dict[str, int]


class MetaRead(ORMModel):
    """Public, non-secret client configuration."""

    app_name: str
    clinic_timezone: str
    appointment_duration_minutes: int
    cancellation_cutoff_hours: int
    booking_window_days: int
    upload_max_bytes: int
    upload_allowed_types: list[str]
    uploads_enabled: bool
    ai_enabled: bool
