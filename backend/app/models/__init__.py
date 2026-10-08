# Import every model here so Alembic autogenerate and metadata.create_all see them.
from app.models.ai import AIConversation, AIMessage
from app.models.appointment import Appointment
from app.models.chat import Conversation, Message, MessageAttachment
from app.models.doctor import (
    Doctor,
    DoctorSchedule,
    DoctorTimeOff,
    Specialization,
    doctor_specializations,
)
from app.models.enums import (
    ACTIVE_APPOINTMENT_STATUSES,
    APPOINTMENT_TRANSITIONS,
    AIMessageRole,
    AppointmentStatus,
    MessageType,
    NotificationType,
    Role,
    TimeOffKind,
)
from app.models.notification import AuditLog, Notification
from app.models.patient import Patient
from app.models.user import User

__all__ = [
    "ACTIVE_APPOINTMENT_STATUSES",
    "APPOINTMENT_TRANSITIONS",
    "AIConversation",
    "AIMessage",
    "AIMessageRole",
    "Appointment",
    "AppointmentStatus",
    "AuditLog",
    "Conversation",
    "Doctor",
    "DoctorSchedule",
    "DoctorTimeOff",
    "Message",
    "MessageAttachment",
    "MessageType",
    "Notification",
    "NotificationType",
    "Patient",
    "Role",
    "Specialization",
    "TimeOffKind",
    "User",
    "doctor_specializations",
]
