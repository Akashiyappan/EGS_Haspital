from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile, status

from app.api.deps import CurrentUser, DbSession, UserPendingPasswordChange, user_rate_limit
from app.core.config import settings
from app.integrations.storage import ImageStorage, get_storage, read_validated_image
from app.models import Role, User
from app.schemas.common import error_responses
from app.schemas.user import MeRead, PatientProfileRead, ProfileUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


async def build_me(db: DbSession, user: User) -> MeRead:
    me = MeRead.model_validate(user)
    if user.role == Role.PATIENT:
        patient = await user_service.get_patient_profile(db, user.id)
        me.patient = PatientProfileRead.model_validate(patient) if patient else None
    elif user.role == Role.DOCTOR:
        me.doctor_id = await user_service.get_doctor_id(db, user.id)
    return me


@router.get(
    "/me",
    response_model=MeRead,
    summary="Current user",
    description="Available even while a temporary password must still be changed.",
    responses=error_responses(401),
)
async def read_me(user: UserPendingPasswordChange, db: DbSession) -> MeRead:
    return await build_me(db, user)


@router.patch(
    "/me",
    response_model=MeRead,
    summary="Update own profile",
    description="Name and phone for everyone; date of birth, gender and emergency contact for patients.",
    responses=error_responses(401, 403, 422),
)
async def update_me(body: ProfileUpdate, user: CurrentUser, db: DbSession) -> MeRead:
    await user_service.update_profile(db, user, body)
    await db.commit()
    return await build_me(db, user)


@router.post(
    "/me/avatar",
    response_model=MeRead,
    summary="Upload a profile image",
    description=(
        f"JPEG, PNG or WebP up to {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB, "
        "validated by file content. Stored in Cloudinary."
    ),
    responses=error_responses(400, 401, 413, 429, 503),
    dependencies=[Depends(user_rate_limit("upload", settings.RATE_LIMIT_UPLOAD))],
)
async def upload_avatar(
    user: CurrentUser,
    db: DbSession,
    storage: Annotated[ImageStorage, Depends(get_storage)],
    file: Annotated[UploadFile, File(description="Image file")],
) -> MeRead:
    data, content_type = await read_validated_image(file)
    image = await storage.upload_image(
        data, folder="avatars", content_type=content_type, private=False
    )
    previous = user.avatar_public_id
    user.avatar_url, user.avatar_public_id = image.url, image.public_id
    await db.commit()
    if previous:
        await storage.delete(previous, "upload")
    return await build_me(db, user)


@router.delete(
    "/me/avatar",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the profile image",
    responses=error_responses(401, 503),
)
async def delete_avatar(
    user: CurrentUser,
    db: DbSession,
    storage: Annotated[ImageStorage, Depends(get_storage)],
) -> None:
    previous = user.avatar_public_id
    user.avatar_url = user.avatar_public_id = None
    await db.commit()
    if previous:
        await storage.delete(previous, "upload")
