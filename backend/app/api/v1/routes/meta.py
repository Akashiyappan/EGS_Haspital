from fastapi import APIRouter

from app.core.config import settings
from app.schemas.notification import MetaRead

router = APIRouter(tags=["meta"])


@router.get(
    "/meta",
    response_model=MetaRead,
    summary="Public client configuration",
    description="Non-secret settings the web client needs (timezone, limits, feature flags).",
)
async def meta() -> MetaRead:
    return MetaRead(
        app_name=settings.APP_NAME,
        clinic_timezone=settings.CLINIC_TIMEZONE,
        appointment_duration_minutes=settings.APPOINTMENT_DURATION_MINUTES,
        cancellation_cutoff_hours=settings.CANCELLATION_CUTOFF_HOURS,
        booking_window_days=settings.BOOKING_WINDOW_DAYS,
        upload_max_bytes=settings.UPLOAD_MAX_BYTES,
        upload_allowed_types=settings.UPLOAD_ALLOWED_IMAGE_TYPES,
        uploads_enabled=settings.cloudinary_configured,
        ai_enabled=settings.ai_configured,
    )
