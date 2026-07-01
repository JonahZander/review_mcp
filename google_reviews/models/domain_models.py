"""Canonical domain models shared across provider, storage, and service layers."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReviewSortOrder(StrEnum):
    """Canonical review sort labels exposed by the service layer."""

    unspecified = "unspecified"
    newest = "newest"
    best = "best"
    worst = "worst"
    most_relevant = "most_relevant"


class CompanyReviewRequest(BaseModel):
    """Input contract for fetching a company review overview."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    company_url: str = Field(..., min_length=1)
    review_limit_per_sort: int = 20
    include_most_relevant: bool = True
    provider: str = Field(default="searchapi", min_length=1)

    @field_validator("review_limit_per_sort")
    @classmethod
    def validate_review_limit_per_sort(cls, value: int) -> int:
        """Accept -1 (fetch all) or any positive integer; reject zero and other negatives."""
        if value == -1 or value >= 1:
            return value
        raise ValueError("review_limit_per_sort must be -1 or >= 1")


class CompanyRecord(BaseModel):
    """Canonical company persistence record."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    company_website_url: str = Field(..., min_length=1)
    normalized_website_domain: str = Field(..., min_length=1)
    display_name: str | None = None
    scraped_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ScrapeRun(BaseModel):
    """Run metadata used to version immutable snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scrape_run_id: str = Field(..., min_length=1)
    company_website_url: str = Field(..., min_length=1)
    scraped_at: datetime
    include_most_relevant: bool
    requested_limit_per_sort: int
    is_current: bool = False

    @field_validator("requested_limit_per_sort")
    @classmethod
    def validate_requested_limit_per_sort(cls, value: int) -> int:
        """Accept -1 (fetch all) or any positive integer; reject zero and other negatives."""
        if value == -1 or value >= 1:
            return value
        raise ValueError("requested_limit_per_sort must be -1 or >= 1")


class DiscoveredPlace(BaseModel):
    """Canonical place identity and metadata discovered for a company."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(..., min_length=1)
    place_id: str = Field(..., min_length=1)
    data_id: str | None = None
    company_website_url: str = Field(..., min_length=1)
    name: str | None = None
    address: str | None = None
    website_domain: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    scraped_at: datetime
    is_deleted: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ReviewRecord(BaseModel):
    """Canonical review record preserving provider order for a given sort bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(..., min_length=1)
    place_id: str = Field(..., min_length=1)
    data_id: str | None = None
    review_id: str = Field(..., min_length=1)
    sort_order: ReviewSortOrder
    sort_rank: int = Field(..., ge=1)
    author_name: str | None = None
    author_contributor_id: str | None = None
    rating: int | None = None
    text: str | None = None
    translated_text: str | None = None
    likes: int | None = None
    written_at: datetime | None = None
    source: str | None = None
    review_link: str | None = None
    scraped_at: datetime
    is_deleted: bool = False
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ReviewHistogram(BaseModel):
    """Canonical review histogram for a place."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(..., min_length=1)
    place_id: str = Field(..., min_length=1)
    data_id: str | None = None
    star_1: int = Field(default=0, ge=0)
    star_2: int = Field(default=0, ge=0)
    star_3: int = Field(default=0, ge=0)
    star_4: int = Field(default=0, ge=0)
    star_5: int = Field(default=0, ge=0)
    total_reviews: int | None = Field(default=None, ge=0)
    scraped_at: datetime
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class LocationOverview(BaseModel):
    """Per-location overview returned in a company review response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(..., min_length=1)
    place_id: str = Field(..., min_length=1)
    data_id: str | None = None
    name: str | None = None
    address: str | None = None
    website_domain: str | None = None
    rating: float | None = None
    reviews_count: int | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    histogram: ReviewHistogram | None = None
    newest_reviews: list[ReviewRecord] = Field(default_factory=list)
    best_reviews: list[ReviewRecord] = Field(default_factory=list)
    worst_reviews: list[ReviewRecord] = Field(default_factory=list)
    most_relevant_reviews: list[ReviewRecord] | None = None


class CompanyReviewOverview(BaseModel):
    """Top-level service output for one company URL."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    company_website_url: str = Field(..., min_length=1)
    normalized_website_domain: str = Field(..., min_length=1)
    scraped_at: datetime
    locations: list[LocationOverview] = Field(default_factory=list)
