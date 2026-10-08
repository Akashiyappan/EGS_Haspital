"""Image storage (Cloudinary). Files are validated by content, not by the
client-declared type, and only metadata is persisted in the database.

Chat images are uploaded with Cloudinary's `authenticated` delivery type: they
are only reachable through signed URLs that the API generates for authorized
users. Profile images use public delivery.
"""

import asyncio
import io
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import AppError, ServiceUnavailableError

logger = logging.getLogger(__name__)

_READ_CHUNK = 64 * 1024

# Magic-number signatures for the image types we can accept.
_SIGNATURES: tuple[tuple[str, bytes, int], ...] = (
    ("image/jpeg", b"\xff\xd8\xff", 0),
    ("image/png", b"\x89PNG\r\n\x1a\n", 0),
    ("image/gif", b"GIF87a", 0),
    ("image/gif", b"GIF89a", 0),
)


class InvalidUploadError(AppError):
    status_code = 400
    code = "invalid_upload"
    message = "Invalid file"


class UploadTooLargeError(AppError):
    status_code = 413
    code = "upload_too_large"
    message = "File is too large"


@dataclass(frozen=True)
class StoredImage:
    public_id: str
    delivery_type: str
    url: str
    content_type: str
    format: str | None
    bytes: int
    width: int | None
    height: int | None


def sniff_image_type(data: bytes) -> str | None:
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    for content_type, signature, offset in _SIGNATURES:
        if data[offset : offset + len(signature)] == signature:
            return content_type
    return None


async def read_validated_image(upload: UploadFile) -> tuple[bytes, str]:
    """Read an upload with a hard size cap and verify it is an allowed image type."""
    limit = settings.UPLOAD_MAX_BYTES
    buffer = bytearray()
    while chunk := await upload.read(_READ_CHUNK):
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise UploadTooLargeError(f"Images must be {limit // (1024 * 1024)} MB or smaller")
    if not buffer:
        raise InvalidUploadError("The file is empty")

    detected = sniff_image_type(bytes(buffer[:16]))
    if detected is None or detected not in settings.UPLOAD_ALLOWED_IMAGE_TYPES:
        allowed = ", ".join(
            t.removeprefix("image/").upper() for t in settings.UPLOAD_ALLOWED_IMAGE_TYPES
        )
        raise InvalidUploadError(
            f"Unsupported image type. Allowed: {allowed}", code="unsupported_type"
        )
    return bytes(buffer), detected


class ImageStorage(Protocol):
    async def upload_image(
        self, data: bytes, *, folder: str, content_type: str, private: bool
    ) -> StoredImage: ...

    async def delete(self, public_id: str, delivery_type: str) -> None: ...

    def url_for(self, public_id: str, delivery_type: str, fmt: str | None) -> str: ...


class CloudinaryStorage:
    def __init__(self) -> None:
        import cloudinary

        cloudinary.config(
            cloud_name=settings.CLOUDINARY_CLOUD_NAME,
            api_key=settings.CLOUDINARY_API_KEY,
            api_secret=settings.CLOUDINARY_API_SECRET.get_secret_value(),
            secure=True,
        )

    async def upload_image(
        self, data: bytes, *, folder: str, content_type: str, private: bool
    ) -> StoredImage:
        import cloudinary.uploader

        delivery_type = "authenticated" if private else "upload"

        def _upload() -> dict[str, Any]:
            result: dict[str, Any] = cloudinary.uploader.upload(
                io.BytesIO(data),
                folder=f"{settings.CLOUDINARY_FOLDER}/{folder}",
                resource_type="image",
                type=delivery_type,
                unique_filename=True,
                overwrite=False,
            )
            return result

        try:
            result = await asyncio.to_thread(_upload)
        except Exception as exc:
            logger.exception("Cloudinary upload failed")
            raise ServiceUnavailableError(
                "Image upload failed. Please try again.", code="upload_failed"
            ) from exc

        return StoredImage(
            public_id=result["public_id"],
            delivery_type=delivery_type,
            url=self.url_for(result["public_id"], delivery_type, result.get("format")),
            content_type=content_type,
            format=result.get("format"),
            bytes=int(result.get("bytes", len(data))),
            width=result.get("width"),
            height=result.get("height"),
        )

    async def delete(self, public_id: str, delivery_type: str) -> None:
        import cloudinary.uploader

        try:
            await asyncio.to_thread(
                cloudinary.uploader.destroy, public_id, type=delivery_type, invalidate=True
            )
        except Exception:  # deleting is best-effort; never fail the user action on it
            logger.exception("Cloudinary delete failed for an asset")

    def url_for(self, public_id: str, delivery_type: str, fmt: str | None) -> str:
        import cloudinary.utils

        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="image",
            type=delivery_type,
            format=fmt,
            secure=True,
            sign_url=delivery_type != "upload",
        )
        return str(url)


@lru_cache
def _cloudinary_storage() -> CloudinaryStorage:
    return CloudinaryStorage()


def get_storage() -> ImageStorage:
    """FastAPI dependency. Tests override it with an in-memory fake."""
    if not settings.cloudinary_configured:
        raise ServiceUnavailableError(
            "Image uploads are not configured on this server", code="uploads_not_configured"
        )
    return _cloudinary_storage()
