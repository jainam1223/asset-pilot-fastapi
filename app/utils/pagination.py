"""Shared pagination convention used by every list endpoint (Assets,
Tickets, and later modules all reuse this instead of inventing their own).
"""

from dataclasses import dataclass

from pydantic import BaseModel, Field

from app.core.config import settings


class PaginationParams(BaseModel):
    """Query-param DTO. Depend on this in routers via `Depends()` so every
    list endpoint gets identical page/page_size/sort semantics for free.
    """

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE)
    sort_by: str | None = None
    sort_order: str = Field(default="asc", pattern="^(asc|desc)$")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PaginationMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


@dataclass
class Page[T]:
    """Return type for repository/service `list_paginated()`-style methods:
    the items for this page plus the total count needed to build
    `PaginationMeta` without a second round trip's worth of logic scattered
    across callers.
    """

    items: list[T]
    total_items: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return -(-self.total_items // self.page_size)  # ceil division

    def to_meta(self) -> PaginationMeta:
        return PaginationMeta(
            page=self.page,
            page_size=self.page_size,
            total_items=self.total_items,
            total_pages=self.total_pages,
        )
