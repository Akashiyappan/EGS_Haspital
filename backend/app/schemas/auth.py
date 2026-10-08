from typing import Literal

from pydantic import BaseModel, Field

from app.models.enums import Role
from app.schemas.user import NormalizedEmail, Password


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)
    portal: Literal["patient", "staff"] = Field(
        default="patient",
        description="`patient` accepts patients only; `staff` accepts admins and doctors.",
    )


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int
    role: Role
    must_change_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class ForgotPasswordRequest(BaseModel):
    email: NormalizedEmail


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=2048)
    new_password: Password
