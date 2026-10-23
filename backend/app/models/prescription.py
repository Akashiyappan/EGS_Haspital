from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import PrescriptionRequestStatus

if TYPE_CHECKING:
    from app.models.appointment import Appointment
    from app.models.doctor import Doctor
    from app.models.patient import Patient
    from app.models.user import User


class PrescriptionRequest(TimestampMixin, Base):
    """Patient request for a doctor to review and issue a prescription."""

    __tablename__ = "prescription_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"), nullable=False)
    appointment_id: Mapped[int | None] = mapped_column(ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PrescriptionRequestStatus.PENDING.value)
    patient: Mapped["Patient"] = relationship(lazy="raise")
    doctor: Mapped["Doctor"] = relationship(lazy="raise")

    __table_args__ = (
        Index("ix_prescription_requests_patient_id", "patient_id"),
        Index("ix_prescription_requests_doctor_id", "doctor_id"),
    )


class Prescription(TimestampMixin, Base):
    """Medical e-prescription issued by a doctor to a patient."""

    __tablename__ = "prescriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    appointment_id: Mapped[int | None] = mapped_column(
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id", ondelete="RESTRICT"),
        nullable=False,
    )
    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
    )
    diagnosis: Mapped[str] = mapped_column(String(500), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships
    doctor: Mapped["Doctor"] = relationship(lazy="raise")
    patient: Mapped["Patient"] = relationship(lazy="raise")
    appointment: Mapped["Appointment | None"] = relationship(lazy="raise")
    items: Mapped[list["PrescriptionItem"]] = relationship(
        back_populates="prescription",
        cascade="all, delete-orphan",
        lazy="raise",
        order_by="PrescriptionItem.id",
    )

    __table_args__ = (
        Index("ix_prescriptions_patient_id", "patient_id"),
        Index("ix_prescriptions_doctor_id", "doctor_id"),
        Index("ix_prescriptions_appointment_id", "appointment_id"),
        Index("ix_prescriptions_created_at", "created_at"),
    )


class PrescriptionItem(Base):
    """Individual prescribed medicine / dosage instruction."""

    __tablename__ = "prescription_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    prescription_id: Mapped[int] = mapped_column(
        ForeignKey("prescriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    medicine_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dosage: Mapped[str] = mapped_column(String(100), nullable=False)
    frequency: Mapped[str] = mapped_column(String(100), nullable=False)
    timing: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    instructions: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationship back to prescription
    prescription: Mapped["Prescription"] = relationship(
        back_populates="items",
        lazy="raise",
    )

    __table_args__ = (
        Index("ix_prescription_items_prescription_id", "prescription_id"),
    )
