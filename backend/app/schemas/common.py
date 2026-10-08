import math
from typing import Any

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> "Page[T]":
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if page_size else 0,
        )


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class MessageResponse(BaseModel):
    message: str


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Reusable OpenAPI error documentation for route decorators."""
    descriptions = {
        400: "Bad request",
        401: "Not authenticated",
        403: "Forbidden for this role or resource",
        404: "Not found",
        409: "Conflict",
        422: "Validation error",
        429: "Rate limit exceeded",
        503: "Dependent service unavailable",
    }
    return {
        code: {"model": ErrorResponse, "description": descriptions.get(code, "Error")}
        for code in codes
    }
