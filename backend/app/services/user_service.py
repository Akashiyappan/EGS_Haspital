from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.pagination import LIKE_ESCAPE, PageParams, escape_like
from app.core.security import hash_password
from app.models import Doctor, Patient, Role, User
from app.schemas.user import PatientRegister, ProfileUpdate

EMAIL_TAKEN = "An account with this email already exists"


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.strip().lower()))
    return result.scalar_one_or_none()


async def ensure_email_available(db: AsyncSession, email: str) -> None:
    if await get_by_email(db, email):
        raise ConflictError(EMAIL_TAKEN, code="email_taken")


async def create_patient(db: AsyncSession, data: PatientRegister) -> User:
    """Public self-registration. Always creates a PATIENT; the role is never
    taken from the request."""
    await ensure_email_available(db, data.email)
    user = User(
        email=data.email,
        first_name=data.first_name,
        last_name=data.last_name or None,
        hashed_password=hash_password(data.password),
        role=Role.PATIENT,
    )
    db.add(user)
    try:
        await db.flush()
        db.add(Patient(user_id=user.id))
        await db.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        await db.rollback()
        raise ConflictError(EMAIL_TAKEN, code="email_taken") from exc
    return user


async def get_patient_profile(db: AsyncSession, user_id: int) -> Patient | None:
    patient: Patient | None = await db.scalar(select(Patient).where(Patient.user_id == user_id))
    return patient


async def get_doctor_id(db: AsyncSession, user_id: int) -> int | None:
    doctor_id: int | None = await db.scalar(select(Doctor.id).where(Doctor.user_id == user_id))
    return doctor_id


async def update_profile(db: AsyncSession, user: User, data: ProfileUpdate) -> None:
    changes = data.model_dump(exclude_unset=True)
    for field in ("first_name", "last_name", "phone"):
        if field in changes:
            if field == "first_name" and not changes[field]:
                continue  # first name is required; ignore attempts to blank it
            setattr(user, field, changes[field])

    if user.role == Role.PATIENT:
        patient = await get_patient_profile(db, user.id)
        if patient is not None:
            for field in (
                "date_of_birth",
                "gender",
                "emergency_contact_name",
                "emergency_contact_phone",
            ):
                if field in changes:
                    setattr(patient, field, changes[field])


async def list_users(
    db: AsyncSession,
    page: PageParams,
    *,
    role: Role | None = None,
    search: str | None = None,
    is_active: bool | None = None,
) -> tuple[list[User], int]:
    query = select(User).where(User.deleted_at.is_(None))
    if role is not None:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    if search:
        term = f"%{escape_like(search.strip().lower())}%"
        query = query.where(
            or_(
                func.lower(User.email).like(term, escape=LIKE_ESCAPE),
                func.lower(User.first_name).like(term, escape=LIKE_ESCAPE),
                func.lower(User.last_name).like(term, escape=LIKE_ESCAPE),
            )
        )
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await db.scalars(
        query.order_by(User.created_at.desc(), User.id.desc())
        .limit(page.page_size)
        .offset(page.offset)
    )
    return list(rows), total
