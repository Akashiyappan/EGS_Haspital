"""Sliding-window rate limiting.

The in-memory backend is per process. With several workers each enforces its
own window, so the effective limit is multiplied by the worker count; swap in a
shared backend (e.g. Redis) behind `RateLimitBackend` for strict global limits.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from fastapi import Request

from app.core.config import settings
from app.core.exceptions import AppError


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many requests. Please try again later."

    def __init__(self, retry_after: int) -> None:
        super().__init__()
        self.retry_after = retry_after


def parse_rate(rate: str) -> tuple[int, int]:
    count, _, seconds = rate.partition("/")
    return int(count), int(seconds)


class RateLimitBackend(Protocol):
    async def hit(self, key: str, limit: int, window: int) -> int | None:
        """Record a hit. Returns seconds to wait if the limit is exceeded, else None."""
        ...


class InMemoryRateLimitBackend:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    async def hit(self, key: str, limit: int, window: int) -> int | None:
        now = time.monotonic()
        async with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                return max(1, int(hits[0] + window - now) + 1)
            hits.append(now)
            if len(self._hits) > 50_000:  # bound memory under key churn
                self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > now - window}
            return None

    def reset(self) -> None:
        self._hits.clear()


backend: RateLimitBackend = InMemoryRateLimitBackend()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(
    scope: str, rate: str, *, key: Literal["ip", "user"] = "ip"
) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency factory. `key="user"` requires request.state.user_id
    (set by the auth dependency) and falls back to IP."""
    limit, window = parse_rate(rate)

    async def dependency(request: Request) -> None:
        if not settings.RATE_LIMIT_ENABLED:
            return
        identity = (
            f"user:{request.state.user_id}"
            if key == "user" and getattr(request.state, "user_id", None)
            else f"ip:{client_ip(request)}"
        )
        retry_after = await backend.hit(f"{scope}:{identity}", limit, window)
        if retry_after is not None:
            raise RateLimitedError(retry_after)

    return dependency
