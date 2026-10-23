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
    PrescriptionRequestStatus,
    Role,
    TimeOffKind,
)
from app.models.notification import AuditLog, Notification
from app.models.patient import Patient
from app.models.prescription import Prescription, PrescriptionItem, PrescriptionRequest
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
    "Prescription",
    "PrescriptionItem",
    "PrescriptionRequest",
    "PrescriptionRequestStatus",
    "Role",
    "Specialization",
    "TimeOffKind",
    "User",
    "doctor_specializations",
]
