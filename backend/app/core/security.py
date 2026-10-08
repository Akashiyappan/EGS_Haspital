from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import uuid4

import bcrypt
import jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError

TokenType = Literal["access", "refresh", "password_reset"]

# Used to keep login timing constant when the email does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed_password: str | None) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), (hashed_password or _DUMMY_HASH).encode())
    except ValueError:
        return False


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    version: int,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "ver": version,
        "iat": now,
        "exp": now + expires_delta,
        "jti": uuid4().hex,
        **(extra or {}),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int, token_version: int, role: str) -> str:
    # The role claim is informational for clients; the API always re-reads the
    # role from the database before authorizing.
    return _create_token(
        str(user_id),
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_version,
        {"role": role},
    )


def create_password_reset_token(user_id: int, token_version: int) -> str:
    # Single use: completing a reset bumps token_version, which invalidates it.
    return _create_token(
        str(user_id),
        "password_reset",
        timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
        token_version,
    )


def create_refresh_token(user_id: int, token_version: int) -> str:
    return _create_token(
        str(user_id),
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_version,
    )


def decode_token(token: str, expected_type: TokenType) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "type", "ver"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token", code="invalid_token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type", code="invalid_token")
    return payload
