from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Request, Response, status

from app.api.deps import DbSession, UserPendingPasswordChange
from app.core.config import settings
from app.core.exceptions import AppError, UnauthorizedError
from app.core.rate_limit import rate_limit
from app.models import User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.common import MessageResponse, error_responses
from app.schemas.user import PatientRegister, UserRead
from app.services import audit_service, auth_service, user_service
from app.services.audit_service import AuditAction

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_PATH = f"{settings.API_V1_PREFIX}/auth"
_auth_rate_limit = Depends(rate_limit("auth", settings.RATE_LIMIT_AUTH))

RefreshCookie = Annotated[str | None, Cookie(alias=settings.REFRESH_COOKIE_NAME)]


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def _token_response(response: Response, user: User) -> TokenResponse:
    pair = auth_service.issue_tokens(user)
    _set_refresh_cookie(response, pair.refresh_token)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(
        access_token=pair.access_token,
        expires_in=pair.expires_in,
        role=user.role,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a patient account",
    description="Public self-registration. Always creates a PATIENT; doctors are created by admins.",
    responses=error_responses(409, 422, 429),
    dependencies=[_auth_rate_limit],
)
async def register(body: PatientRegister, request: Request, db: DbSession) -> UserRead:
    user = await user_service.create_patient(db, body)
    audit_service.record(
        db,
        AuditAction.PATIENT_REGISTERED,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    return UserRead.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Log in",
    description=(
        "Returns a short-lived access token and sets a rotating httpOnly refresh cookie. "
        "`portal=patient` accepts patients only, `portal=staff` accepts admins and doctors."
    ),
    responses=error_responses(401, 403, 422, 429),
    dependencies=[_auth_rate_limit],
)
async def login(
    body: LoginRequest, request: Request, response: Response, db: DbSession
) -> TokenResponse:
    try:
        user = await auth_service.authenticate(db, body.email, body.password, body.portal)
    except AppError as exc:
        audit_service.record(
            db,
            AuditAction.LOGIN_FAILED,
            actor_id=None,
            details={"portal": body.portal, "reason": exc.code},
            request=request,
        )
        await db.commit()
        raise
    audit_service.record(
        db,
        AuditAction.LOGIN_SUCCEEDED,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        details={"portal": body.portal},
        request=request,
    )
    await db.commit()
    return _token_response(response, user)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate the refresh cookie and get a new access token",
    responses=error_responses(401),
)
async def refresh(
    response: Response, db: DbSession, refresh_token: RefreshCookie = None
) -> TokenResponse:
    if not refresh_token:
        raise UnauthorizedError("Missing refresh token", code="missing_refresh_token")
    user = await auth_service.resolve_token_user(db, refresh_token, "refresh")
    return _token_response(response, user)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Log out everywhere",
    description="Revokes all of the user's tokens (if the cookie is valid) and clears the cookie.",
)
async def logout(request: Request, db: DbSession, refresh_token: RefreshCookie = None) -> Response:
    if refresh_token:
        try:
            user = await auth_service.resolve_token_user(db, refresh_token, "refresh")
            audit_service.record(
                db,
                AuditAction.LOGOUT,
                actor_id=user.id,
                entity_type="user",
                entity_id=user.id,
                request=request,
            )
            await auth_service.revoke_tokens(db, user)
        except AppError:
            pass  # already invalid; logging out is still successful
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _clear_refresh_cookie(response)
    return response


@router.post(
    "/change-password",
    response_model=TokenResponse,
    summary="Change password",
    description=(
        "Requires the current password. Clears the forced-change flag on temporary "
        "passwords, signs out other sessions and returns fresh tokens for this one."
    ),
    responses=error_responses(400, 401, 422, 429),
    dependencies=[_auth_rate_limit],
)
async def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: UserPendingPasswordChange,
    db: DbSession,
) -> TokenResponse:
    await auth_service.change_password(db, user, body.current_password, body.new_password)
    audit_service.record(
        db,
        AuditAction.PASSWORD_CHANGED,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    return _token_response(response, user)


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email",
    description="Always returns the same response whether or not the email exists.",
    responses=error_responses(422, 429),
    dependencies=[_auth_rate_limit],
)
async def forgot_password(
    body: ForgotPasswordRequest, request: Request, db: DbSession
) -> MessageResponse:
    user = await auth_service.request_password_reset(db, body.email)
    if user is not None:
        audit_service.record(
            db,
            AuditAction.PASSWORD_RESET_REQUESTED,
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            request=request,
        )
        await db.commit()
    return MessageResponse(
        message="If an account exists for that email, a reset link has been sent."
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Set a new password with a reset token",
    responses=error_responses(400, 422, 429),
    dependencies=[_auth_rate_limit],
)
async def reset_password(
    body: ResetPasswordRequest, request: Request, db: DbSession
) -> MessageResponse:
    user = await auth_service.reset_password(db, body.token, body.new_password)
    audit_service.record(
        db,
        AuditAction.PASSWORD_RESET_COMPLETED,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    return MessageResponse(message="Your password has been reset. You can now sign in.")
