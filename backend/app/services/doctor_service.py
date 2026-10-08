from fastapi import Request
from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.pagination import LIKE_ESCAPE, PageParams, escape_like
from app.core.security import hash_password
from app.core.timeutils import utcnow
from app.models import Doctor, NotificationType, Role, Specialization, User
from app.schemas.doctor import (
    DoctorAdminRead,
    DoctorCreate,
    DoctorPublic,
    DoctorUpdate,
    SpecializationRead,
)
from app.services import appointment_service, audit_service, specialization_service
from app.services.audit_service import AuditAction
from app.services.notification_service import NotificationPayload, Notifier
from app.services.user_service import EMAIL_TAKEN, ensure_email_available


def to_public(doctor: Doctor) -> DoctorPublic:
    user = doctor.user
    return DoctorPublic(
        id=doctor.id,
        first_name=user.first_name,
        last_name=user.last_name,
        full_name=user.full_name,
        avatar_url=user.avatar_url,
        qualification=doctor.qualification,
        experience_years=doctor.experience_years,
        bio=doctor.bio,
        specializations=[SpecializationRead.model_validate(s) for s in doctor.specializations],
    )


def to_admin(doctor: Doctor) -> DoctorAdminRead:
    user = doctor.user
    return DoctorAdminRead(
        **to_public(doctor).model_dump(),
        user_id=user.id,
        email=user.email,
        phone=user.phone,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        created_at=doctor.created_at,
    )


def _base_query(*, public: bool) -> Select[tuple[Doctor]]:
    query = select(Doctor).join(User, Doctor.user_id == User.id).where(User.deleted_at.is_(None))
    if public:
        query = query.where(User.is_active.is_(True))
    return query


async def list_doctors(
    db: AsyncSession,
    page: PageParams,
    *,
    public: bool,
    search: str | None = None,
    specialization_id: int | None = None,
    is_active: bool | None = None,
) -> tuple[list[Doctor], int]:
    query = _base_query(public=public)
    if not public and is_active is not None:
        query = query.where(User.is_active == is_active)
    if specialization_id is not None:
        query = query.where(Doctor.specializations.any(Specialization.id == specialization_id))
    if search:
        term = f"%{escape_like(search.strip().lower())}%"
        conditions = [
            func.lower(User.first_name).like(term, escape=LIKE_ESCAPE),
            func.lower(User.last_name).like(term, escape=LIKE_ESCAPE),
            Doctor.specializations.any(
                func.lower(Specialization.name).like(term, escape=LIKE_ESCAPE)
            ),
        ]
        if not public:  # patients can't search by contact details
            conditions.append(func.lower(User.email).like(term, escape=LIKE_ESCAPE))
        query = query.where(or_(*conditions))
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(User.first_name, User.last_name, Doctor.id)
        .limit(page.page_size)
        .offset(page.offset)
    )
    return list(rows), total


async def get_public_by_ids(db: AsyncSession, ids: set[int]) -> dict[int, Doctor]:
    if not ids:
        return {}
    rows = await db.scalars(_base_query(public=True).where(Doctor.id.in_(ids)))
    return {doctor.id: doctor for doctor in rows}


async def get_doctor(db: AsyncSession, doctor_id: int, *, public: bool) -> Doctor:
    doctor = await db.scalar(_base_query(public=public).where(Doctor.id == doctor_id))
    if doctor is None:
        raise NotFoundError("Doctor not found")
    return doctor


async def create_doctor(
    db: AsyncSession, data: DoctorCreate, actor: User, request: Request | None
) -> Doctor:
    await ensure_email_available(db, data.email)
    specializations = await specialization_service.get_active_by_ids(db, data.specialization_ids)
    user = User(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name or None,
        phone=data.phone,
        hashed_password=hash_password(data.temporary_password),
        role=Role.DOCTOR,
        is_active=data.is_active,
        must_change_password=True,
    )
    doctor = Doctor(
        user=user,
        qualification=data.qualification,
        experience_years=data.experience_years,
        bio=data.bio,
        specializations=specializations,
    )
    db.add(doctor)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError(EMAIL_TAKEN, code="email_taken") from exc
    audit_service.record(
        db,
        AuditAction.DOCTOR_CREATED,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        details={"user_id": user.id, "specialization_ids": data.specialization_ids},
        request=request,
    )
    await db.commit()
    return await get_doctor(db, doctor.id, public=False)


async def update_doctor(
    db: AsyncSession, doctor: Doctor, data: DoctorUpdate, actor: User, request: Request | None
) -> Doctor:
    changes = data.model_dump(exclude_unset=True)
    user = doctor.user
    for field in ("first_name", "last_name", "phone"):
        if field in changes and (field != "first_name" or changes[field]):
            setattr(user, field, changes[field])
    for field in ("qualification", "bio"):
        if field in changes:
            setattr(doctor, field, changes[field])
    if changes.get("experience_years") is not None:
        doctor.experience_years = changes["experience_years"]
    if changes.get("specialization_ids") is not None:
        doctor.specializations = await specialization_service.get_active_by_ids(
            db, changes["specialization_ids"]
        )
    audit_service.record(
        db,
        AuditAction.DOCTOR_UPDATED,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        details={"fields": sorted(changes)},
        request=request,
    )
    await db.commit()
    return await get_doctor(db, doctor.id, public=False)


async def set_active(
    db: AsyncSession,
    doctor: Doctor,
    is_active: bool,
    actor: User,
    request: Request | None,
    reason: str | None = None,
) -> int:
    """Activate/deactivate. Deactivation signs the doctor out and cancels their
    upcoming appointments (patients are notified). Returns the cancel count."""
    user = doctor.user
    cancelled = 0
    notifier = Notifier(db)
    if user.is_active and not is_active:
        user.token_version += 1
        cancelled = await appointment_service.cancel_future_for_doctor(
            db, doctor, actor, reason or "The doctor is no longer available", notifier
        )
    user.is_active = is_active
    audit_service.record(
        db,
        AuditAction.DOCTOR_ACTIVATED if is_active else AuditAction.DOCTOR_DEACTIVATED,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        details={"cancelled_appointments": cancelled},
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
    return cancelled


async def soft_delete(
    db: AsyncSession, doctor: Doctor, actor: User, request: Request | None
) -> int:
    """Soft delete: history (appointments, chats, audit) is preserved for
    medical-record integrity; the account can no longer sign in or be booked."""
    notifier = Notifier(db)
    cancelled = await appointment_service.cancel_future_for_doctor(
        db, doctor, actor, "The doctor is no longer available", notifier
    )
    user = doctor.user
    user.is_active = False
    user.deleted_at = utcnow()
    user.token_version += 1
    audit_service.record(
        db,
        AuditAction.DOCTOR_DELETED,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        details={"cancelled_appointments": cancelled},
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
    return cancelled


async def reset_password(
    db: AsyncSession, doctor: Doctor, temporary_password: str, actor: User, request: Request | None
) -> None:
    user = doctor.user
    user.hashed_password = hash_password(temporary_password)
    user.must_change_password = True
    user.token_version += 1
    notifier = Notifier(db)
    await notifier.add(
        user.id,
        NotificationPayload(
            NotificationType.ACCOUNT,
            "Password reset by administrator",
            "An administrator issued you a new temporary password. "
            "You will be asked to change it when you sign in.",
        ),
    )
    audit_service.record(
        db,
        AuditAction.DOCTOR_PASSWORD_RESET,
        actor_id=actor.id,
        entity_type="doctor",
        entity_id=doctor.id,
        request=request,
    )
    await db.commit()
    await notifier.dispatch()
