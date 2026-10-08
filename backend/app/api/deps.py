from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models import Doctor, Patient, Role, User
from app.services import auth_service

DbSession = Annotated[AsyncSession, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]


async def _authenticate(request: Request, db: AsyncSession, credentials: BearerCredentials) -> User:
    if credentials is None:
        raise UnauthorizedError()
    # Role and status always come from the database, never from client-supplied claims.
    user = await auth_service.resolve_token_user(db, credentials.credentials, "access")
    request.state.user_id = user.id
    return user


async def get_user_pending_password_change(
    request: Request, db: DbSession, credentials: BearerCredentials
) -> User:
    """Authenticated user, even if they still have to replace a temporary password.
    Only for the handful of endpoints needed to do exactly that."""
    return await _authenticate(request, db, credentials)


async def get_current_user(request: Request, db: DbSession, credentials: BearerCredentials) -> User:
    user = await _authenticate(request, db, credentials)
    if user.must_change_password:
        raise ForbiddenError(
            "You must change your temporary password before continuing",
            code="password_change_required",
        )
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
UserPendingPasswordChange = Annotated[User, Depends(get_user_pending_password_change)]


def require_roles(*roles: Role):  # type: ignore[no-untyped-def]
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise ForbiddenError()
        return user

    return dependency


AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
DoctorUser = Annotated[User, Depends(require_roles(Role.DOCTOR))]
PatientUser = Annotated[User, Depends(require_roles(Role.PATIENT))]


async def get_current_doctor(user: DoctorUser, db: DbSession) -> Doctor:
    doctor = await db.scalar(select(Doctor).where(Doctor.user_id == user.id))
    if doctor is None:
        raise ForbiddenError("Doctor profile not found", code="profile_missing")
    return doctor


async def get_current_patient(user: PatientUser, db: DbSession) -> Patient:
    patient = await db.scalar(select(Patient).where(Patient.user_id == user.id))
    if patient is None:
        raise ForbiddenError("Patient profile not found", code="profile_missing")
    return patient


CurrentDoctor = Annotated[Doctor, Depends(get_current_doctor)]
CurrentPatient = Annotated[Patient, Depends(get_current_patient)]


def user_rate_limit(scope: str, rate: str) -> Callable[..., Awaitable[None]]:
    """Per-user rate limit. Depends on authentication so the user id is known
    (a plain route-level dependency would run before auth and fall back to IP)."""
    limiter = rate_limit(scope, rate, key="user")

    async def dependency(request: Request, _: CurrentUser) -> None:
        await limiter(request)

    return dependency
