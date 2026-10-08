from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

from app.core.config import settings


@dataclass(frozen=True)
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def _page_params(
    page: Annotated[int, Query(ge=1, le=10_000, description="1-based page number")] = 1,
    page_size: Annotated[
        int | None, Query(ge=1, description=f"Items per page (max {settings.MAX_PAGE_SIZE})")
    ] = None,
) -> PageParams:
    size = min(page_size or settings.DEFAULT_PAGE_SIZE, settings.MAX_PAGE_SIZE)
    return PageParams(page=page, page_size=size)


Pagination = Annotated[PageParams, Depends(_page_params)]


LIKE_ESCAPE = "!"


def escape_like(term: str) -> str:
    """Escape LIKE wildcards in user search input; use with escape=LIKE_ESCAPE.
    "!" avoids backslash, which MySQL also treats as a string-literal escape."""
    return term.replace("!", "!!").replace("%", "!%").replace("_", "!_")
