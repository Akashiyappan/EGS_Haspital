from datetime import datetime

from sqlalchemy import CheckConstraint, Computed, Enum, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime
from app.models.doctor import Doctor
from app.models.enums import AppointmentStatus
from app.models.patient import Patient

# Keep in sync with enums.ACTIVE_APPOINTMENT_STATUSES.
_ACTIVE_SLOT = "CASE WHEN status IN ('BOOKED', 'CONFIRMED') THEN starts_at ELSE NULL END"


class Appointment(TimestampMixin, Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="RESTRICT"))
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(
            AppointmentStatus,
            native_enum=False,
            length=16,
            create_constraint=True,
            name="appointment_status",
        ),
        default=AppointmentStatus.BOOKED,
    )
    reason: Mapped[str | None] = mapped_column(Text)
    doctor_notes: Mapped[str | None] = mapped_column(Text)
    cancellation_reason: Mapped[str | None] = mapped_column(String(500))
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reminder_sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Database-generated: equals starts_at while the appointment holds its slot
    # (BOOKED/CONFIRMED), NULL otherwise. Never written by the application.
    active_slot_starts_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime(), Computed(_ACTIVE_SLOT, persisted=True)
    )

    doctor: Mapped[Doctor] = relationship(lazy="raise")
    patient: Mapped[Patient] = relationship(lazy="raise")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="time_range"),
        # Double-booking protection lives in the database. MySQL has no partial
        # indexes, so uniqueness is on the generated column: active appointments
        # collide on (doctor_id, starts_at); cancelled/finished ones are NULL, and
        # a unique index allows any number of NULLs. Enforced atomically even
        # under concurrent requests.
        Index(
            "uq_appointments_doctor_active_slot",
            "doctor_id",
            "active_slot_starts_at",
            unique=True,
        ),
        Index(
            "uq_appointments_patient_active_slot",
            "patient_id",
            "active_slot_starts_at",
            unique=True,
        ),
        Index("ix_appointments_doctor_starts_at", "doctor_id", "starts_at"),
        Index("ix_appointments_patient_starts_at", "patient_id", "starts_at"),
        Index("ix_appointments_status_starts_at", "status", "starts_at"),
    )
