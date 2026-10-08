import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    return {"status": "ok", "version": settings.APP_VERSION}


@router.get("/ready", summary="Readiness probe (checks the database)")
async def readiness(db: DbSession) -> JSONResponse:
    try:
        await db.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Readiness check failed")
        return JSONResponse(
            {"status": "unavailable", "database": "down"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse({"status": "ok", "database": "up"})
