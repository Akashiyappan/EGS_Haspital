from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    Time,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime
from app.models.enums import TimeOffKind
from app.models.user import User

doctor_specializations = Table(
    "doctor_specializations",
    Base.metadata,
    Column("doctor_id", ForeignKey("doctors.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "specialization_id",
        ForeignKey("specializations.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    ),
)


class Specialization(TimestampMixin, Base):
    __tablename__ = "specializations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())


class Doctor(TimestampMixin, Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    qualification: Mapped[str | None] = mapped_column(String(255))
    experience_years: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    bio: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
    specializations: Mapped[list[Specialization]] = relationship(
        secondary=doctor_specializations, lazy="selectin", order_by=Specialization.name
    )

    __table_args__ = (
        CheckConstraint("experience_years >= 0 AND experience_years <= 80", name="experience"),
    )


class DoctorSchedule(TimestampMixin, Base):
    """A recurring weekly working period, in clinic-local wall-clock time.

    Several rows per weekday model multiple shifts; effective_from/until model
    temporary or seasonal schedules.
    """

    __tablename__ = "doctor_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday … 6 = Sunday
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    slot_minutes: Mapped[int] = mapped_column(SmallInteger)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday"),
        CheckConstraint("end_time > start_time", name="time_range"),
        CheckConstraint("slot_minutes > 0", name="slot_minutes"),
        Index("ix_doctor_schedules_doctor_weekday", "doctor_id", "weekday"),
    )


class DoctorTimeOff(TimestampMixin, Base):
    """Leave, holidays and ad-hoc unavailability. doctor_id NULL = clinic-wide."""

    __tablename__ = "doctor_time_off"

    id: Mapped[int] = mapped_column(primary_key=True)
    doctor_id: Mapped[int | None] = mapped_column(ForeignKey("doctors.id", ondelete="CASCADE"))
    kind: Mapped[TimeOffKind] = mapped_column(
        Enum(
            TimeOffKind, native_enum=False, length=16, create_constraint=True, name="time_off_kind"
        )
    )
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    reason: Mapped[str | None] = mapped_column(String(255))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="time_range"),
        Index("ix_doctor_time_off_doctor_range", "doctor_id", "starts_at", "ends_at"),
    )
