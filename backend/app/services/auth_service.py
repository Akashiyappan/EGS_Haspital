import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError, ForbiddenError, UnauthorizedError
from app.core.security import (
    TokenType,
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.timeutils import utcnow
from app.integrations.email import EmailMessage, get_email_sender
from app.models import Role, User
from app.services import user_service

logger = logging.getLogger(__name__)

Portal = Literal["patient", "staff"]

PORTAL_ROLES: dict[Portal, frozenset[Role]] = {
    "patient": frozenset({Role.PATIENT}),
    "staff": frozenset({Role.ADMIN, Role.DOCTOR}),
}


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


def issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.token_version, user.role.value),
        refresh_token=create_refresh_token(user.id, user.token_version),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def authenticate(db: AsyncSession, email: str, password: str, portal: Portal) -> User:
    user = await user_service.get_by_email(db, email)
    # Always run a bcrypt check so response time doesn't reveal whether the email exists.
    password_ok = verify_password(password, user.hashed_password if user else None)
    # Wrong portal looks exactly like wrong credentials, so roles can't be probed.
    if (
        user is None
        or not password_ok
        or user.deleted_at is not None
        or user.role not in PORTAL_ROLES[portal]
    ):
        raise UnauthorizedError("Invalid email or password", code="invalid_credentials")
    if not user.is_active:
        raise ForbiddenError("This account is disabled", code="inactive_user")
    user.last_login_at = utcnow()
    return user


async def resolve_token_user(db: AsyncSession, token: str, token_type: TokenType) -> User:
    payload = decode_token(token, token_type)
    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError) as exc:
        raise UnauthorizedError("Invalid token", code="invalid_token") from exc

    user = await user_service.get_by_id(db, user_id)
    if (
        user is None
        or not user.is_active
        or user.deleted_at is not None
        or payload["ver"] != user.token_version
    ):
        raise UnauthorizedError("Invalid token", code="invalid_token")
    return user


async def revoke_tokens(db: AsyncSession, user: User) -> None:
    user.token_version += 1
    await db.commit()


def _set_password(user: User, new_password: str) -> None:
    user.hashed_password = hash_password(new_password)
    user.must_change_password = False
    user.token_version += 1  # signs out every other session


async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.hashed_password):
        raise AppError("Current password is incorrect", code="invalid_current_password")
    if current_password == new_password:
        raise AppError("New password must be different", code="password_unchanged")
    _set_password(user, new_password)


async def request_password_reset(db: AsyncSession, email: str) -> User | None:
    """Emails a single-use reset link. Returns the user (for auditing) or None.
    Callers must respond identically either way to avoid account enumeration."""
    user = await user_service.get_by_email(db, email)
    if user is None or not user.is_active or user.deleted_at is not None:
        return None
    token = create_password_reset_token(user.id, user.token_version)
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password#token={token}"
    await get_email_sender().send(
        EmailMessage(
            to=user.email,
            subject="Reset your password",
            text=(
                f"Hello {user.first_name},\n\nUse the link below to set a new password. "
                f"It expires in {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes and can be "
                f"used once.\n\n{link}\n\nIf you did not ask for this, ignore this email."
            ),
        )
    )
    return user


async def reset_password(db: AsyncSession, token: str, new_password: str) -> User:
    try:
        user = await resolve_token_user(db, token, "password_reset")
    except UnauthorizedError as exc:
        raise AppError(
            "This reset link is invalid or has expired", code="invalid_reset_token"
        ) from exc
    _set_password(user, new_password)
    return user
