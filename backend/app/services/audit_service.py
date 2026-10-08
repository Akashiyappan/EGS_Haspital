from enum import StrEnum
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import request_id_ctx
from app.core.rate_limit import client_ip
from app.models import AuditLog


class AuditAction(StrEnum):
    LOGIN_SUCCEEDED = "auth.login_succeeded"
    LOGIN_FAILED = "auth.login_failed"
    LOGOUT = "auth.logout"
    PASSWORD_CHANGED = "auth.password_changed"
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"
    PATIENT_REGISTERED = "patient.registered"
    DOCTOR_CREATED = "doctor.created"
    DOCTOR_UPDATED = "doctor.updated"
    DOCTOR_ACTIVATED = "doctor.activated"
    DOCTOR_DEACTIVATED = "doctor.deactivated"
    DOCTOR_DELETED = "doctor.deleted"
    DOCTOR_PASSWORD_RESET = "doctor.password_reset"
    USER_ACTIVATED = "user.activated"
    USER_DEACTIVATED = "user.deactivated"
    SCHEDULE_CHANGED = "schedule.changed"
    TIME_OFF_ADDED = "time_off.added"
    TIME_OFF_REMOVED = "time_off.removed"
    SPECIALIZATION_CREATED = "specialization.created"
    SPECIALIZATION_UPDATED = "specialization.updated"
    APPOINTMENT_BOOKED = "appointment.booked"
    APPOINTMENT_STATUS_CHANGED = "appointment.status_changed"


def record(
    db: AsyncSession,
    action: AuditAction,
    *,
    actor_id: int | None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
) -> None:
    """Stage an audit entry in the current transaction (committed with it).

    `details` must never contain passwords, tokens, secrets or clinical free text.
    """
    db.add(
        AuditLog(
            actor_id=actor_id,
            action=action.value,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details or {},
            ip_address=client_ip(request) if request else None,
            request_id=request_id_ctx.get() if request_id_ctx.get() != "-" else None,
        )
    )
