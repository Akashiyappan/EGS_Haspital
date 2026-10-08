import re
from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.models.enums import Role
from app.schemas.common import ORMModel

_PHONE_RE = re.compile(r"^\+?[0-9][0-9 ()-]{6,19}$")


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _check_password(value: str) -> str:
    # bcrypt only considers the first 72 bytes and rejects longer input.
    if len(value.encode()) > 72:
        raise ValueError("Password is too long")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one number")
    return value


def _check_phone(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if not _PHONE_RE.match(value):
        raise ValueError("Enter a valid phone number")
    return value


NormalizedEmail = Annotated[EmailStr, AfterValidator(_normalize_email)]
Password = Annotated[str, Field(min_length=8, max_length=72), AfterValidator(_check_password)]
PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionalName = Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=100)]
Phone = Annotated[
    str | None, StringConstraints(strip_whitespace=True), AfterValidator(_check_phone)
]


class PatientRegister(BaseModel):
    first_name: PersonName
    last_name: OptionalName = None
    email: NormalizedEmail
    password: Password


class UserRead(ORMModel):
    id: int
    email: str
    role: Role
    first_name: str
    last_name: str | None
    full_name: str
    phone: str | None
    avatar_url: str | None
    is_active: bool
    must_change_password: bool
    created_at: datetime


class PatientProfileRead(ORMModel):
    id: int
    date_of_birth: date | None
    gender: str | None
    emergency_contact_name: str | None
    emergency_contact_phone: str | None


class MeRead(UserRead):
    patient: PatientProfileRead | None = None
    doctor_id: int | None = None


class ProfileUpdate(BaseModel):
    """Self-service profile fields. Patient-only fields are ignored for other roles."""

    first_name: PersonName | None = None
    last_name: OptionalName = None
    phone: Phone = None
    date_of_birth: date | None = None
    gender: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=32)] = None
    emergency_contact_name: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=200)
    ] = None
    emergency_contact_phone: Phone = None


class AdminUserRead(UserRead):
    last_login_at: datetime | None
    deleted_at: datetime | None


class UserStatusUpdate(BaseModel):
    is_active: bool
