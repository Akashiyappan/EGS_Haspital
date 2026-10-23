from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    PATIENT = "PATIENT"


class AppointmentStatus(StrEnum):
    BOOKED = "BOOKED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


# Statuses that occupy a slot. Mirrored by the generated column appointments.active_slot_starts_at.
ACTIVE_APPOINTMENT_STATUSES = frozenset({AppointmentStatus.BOOKED, AppointmentStatus.CONFIRMED})

# The appointment state machine. Anything not listed here is rejected.
APPOINTMENT_TRANSITIONS: dict[AppointmentStatus, frozenset[AppointmentStatus]] = {
    AppointmentStatus.BOOKED: frozenset({AppointmentStatus.CONFIRMED, AppointmentStatus.CANCELLED}),
    AppointmentStatus.CONFIRMED: frozenset(
        {AppointmentStatus.COMPLETED, AppointmentStatus.CANCELLED, AppointmentStatus.NO_SHOW}
    ),
    AppointmentStatus.CANCELLED: frozenset(),
    AppointmentStatus.COMPLETED: frozenset(),
    AppointmentStatus.NO_SHOW: frozenset(),
}


class TimeOffKind(StrEnum):
    LEAVE = "LEAVE"
    HOLIDAY = "HOLIDAY"
    UNAVAILABLE = "UNAVAILABLE"


class MessageType(StrEnum):
    TEXT = "TEXT"
    IMAGE = "IMAGE"


class AIMessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class PrescriptionRequestStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"


class NotificationType(StrEnum):
    APPOINTMENT_BOOKED = "APPOINTMENT_BOOKED"
    APPOINTMENT_CONFIRMED = "APPOINTMENT_CONFIRMED"
    APPOINTMENT_CANCELLED = "APPOINTMENT_CANCELLED"
    APPOINTMENT_UPDATED = "APPOINTMENT_UPDATED"
    APPOINTMENT_REMINDER = "APPOINTMENT_REMINDER"
    SCHEDULE_CHANGED = "SCHEDULE_CHANGED"
    NEW_MESSAGE = "NEW_MESSAGE"
    ACCOUNT = "ACCOUNT"
    PRESCRIPTION_ISSUED = "PRESCRIPTION_ISSUED"
    PRESCRIPTION_REQUESTED = "PRESCRIPTION_REQUESTED"
    PRESCRIPTION_DECLINED = "PRESCRIPTION_DECLINED"
