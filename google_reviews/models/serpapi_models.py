"""Spec-aligned Pydantic models for SerpAPI Google Maps and Google Maps Reviews."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SerpApiMapsParams(BaseModel):
    """Parameters for SerpAPI Google Maps endpoint."""

    q: str
    ll: str | None = None
    hl: str | None = None
    gl: str | None = None
    start: int | None = Field(default=None, ge=0)
    type: str | None = None
    no_cache: bool | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Serialise non-None fields and inject the engine key."""
        query_params = self.model_dump(exclude_none=True)
        query_params["engine"] = "google_maps"
        return query_params


class SerpApiMapsReviewsParams(BaseModel):
    """Parameters for SerpAPI Google Maps Reviews endpoint."""

    place_id: str | None = None
    data_id: str | None = None
    hl: str | None = None
    gl: str | None = None
    query: str | None = None
    topic_id: str | None = None
    sort_by: Literal["qualityScore", "newestFirst", "ratingHigh", "ratingLow"] | None = None
    num: int | None = Field(default=None, ge=1, le=20)
    next_page_token: str | None = None

    @model_validator(mode="after")
    def validate_ids(self) -> SerpApiMapsReviewsParams:
        """Require exactly one of place_id or data_id (SerpAPI rejects requests with both)."""
        if bool(self.place_id) == bool(self.data_id):
            raise ValueError("Exactly one of place_id or data_id must be provided.")
        return self

    def to_query_params(self) -> dict[str, Any]:
        """Serialise non-None fields and inject the engine key."""
        query_params = self.model_dump(exclude_none=True)
        query_params["engine"] = "google_maps_reviews"
        return query_params


class SerpApiSearchMetadata(BaseModel):
    """Common SerpAPI search metadata payload."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    status: str | None = None
    created_at: str | None = None
    request_time_taken: float | None = None
    parsing_time_taken: float | None = None
    total_time_taken: float | None = None
    request_url: str | None = None
    html_url: str | None = None
    json_url: str | None = None


class SerpApiRatingHistogram(BaseModel):
    """Ratings histogram object with star buckets from 1 to 5."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    one_star: int | None = Field(default=None, alias="1")
    two_star: int | None = Field(default=None, alias="2")
    three_star: int | None = Field(default=None, alias="3")
    four_star: int | None = Field(default=None, alias="4")
    five_star: int | None = Field(default=None, alias="5")


class SerpApiRatingSummaryEntry(BaseModel):
    """Rating summary row used by some reviews payloads."""

    model_config = ConfigDict(extra="allow")

    stars: int | None = None
    amount: int | None = None


class SerpApiMapsLinks(BaseModel):
    """Link bundle in map local result rows."""

    model_config = ConfigDict(extra="allow")

    website: str | None = None
    directions: str | None = None
    reviews: str | None = None


class SerpApiMapsLocalResult(BaseModel):
    """Local result row from SerpAPI Google Maps."""

    model_config = ConfigDict(extra="allow")

    position: int | None = None
    place_id: str | None = None
    data_id: str | None = None
    title: str | None = None
    address: str | None = None
    rating: float | None = None
    reviews: int | None = None
    website: str | None = None
    domain: str | None = None
    links: SerpApiMapsLinks | None = None
    type: str | None = None
    types: list[str] = Field(default_factory=list)


class SerpApiMapsSearchParameters(BaseModel):
    """Google Maps search parameters block."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None
    q: str | None = None
    ll: str | None = None
    hl: str | None = None
    gl: str | None = None
    start: int | None = None
    type: str | None = None


class SerpApiMapsResponse(BaseModel):
    """Typed response envelope for SerpAPI Google Maps search."""

    model_config = ConfigDict(extra="allow")

    search_metadata: SerpApiSearchMetadata | None = None
    search_parameters: SerpApiMapsSearchParameters | None = None
    local_results: list[SerpApiMapsLocalResult] = Field(default_factory=list)
    error: str | None = None


class SerpApiMapsReviewsPlaceResult(BaseModel):
    """Place summary object in SerpAPI reviews response."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    address: str | None = None
    phone: str | None = None
    rating: float | None = None
    reviews: int | None = None
    reviews_histogram: SerpApiRatingHistogram | None = None
    rating_summary: list[SerpApiRatingSummaryEntry] = Field(default_factory=list)
    type: str | None = None


class SerpApiMapsReviewUser(BaseModel):
    """Review author payload."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    link: str | None = None
    contributor_id: str | None = None
    is_local_guide: bool | None = None
    local_guide: bool | None = None
    reviews: int | None = None
    photos: int | None = None
    thumbnail: str | None = None


class SerpApiMapsReviewResponse(BaseModel):
    """Business response attached to a review."""

    model_config = ConfigDict(extra="allow")

    date: str | None = None
    iso_date: str | None = None
    text: str | None = None


class SerpApiMapsReview(BaseModel):
    """Review entry from SerpAPI Google Maps Reviews endpoint."""

    model_config = ConfigDict(extra="allow")

    review_id: str | None = None
    id: str | None = None
    user: SerpApiMapsReviewUser | None = None
    link: str | None = None
    source: str | None = None
    text: str | None = None
    snippet: str | None = None
    translated_text: str | None = None
    rating: int | None = None
    date: str | None = None
    iso_date: str | None = None
    likes: int | None = None
    response: SerpApiMapsReviewResponse | None = None


class SerpApiMapsReviewsPagination(BaseModel):
    """Pagination block in SerpAPI reviews response."""

    model_config = ConfigDict(extra="allow")

    next_page_token: str | None = None
    next: str | None = None


class SerpApiMapsReviewsSearchParameters(BaseModel):
    """Google Maps Reviews search parameters block."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None
    data_id: str | None = None
    place_id: str | None = None
    query: str | None = None
    topic_id: str | None = None
    sort_by: str | None = None
    hl: str | None = None
    gl: str | None = None
    num: int | str | None = None
    next_page_token: str | None = None


class SerpApiMapsReviewsResponse(BaseModel):
    """Typed response envelope for SerpAPI Google Maps Reviews."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    search_metadata: SerpApiSearchMetadata | None = None
    search_parameters: SerpApiMapsReviewsSearchParameters | None = None
    place_result: SerpApiMapsReviewsPlaceResult | None = None
    place_info: SerpApiMapsReviewsPlaceResult | None = None
    topics: list[dict[str, Any]] = Field(default_factory=list)
    reviews: list[SerpApiMapsReview] = Field(default_factory=list)
    pagination: SerpApiMapsReviewsPagination | None = Field(default=None, alias="serpapi_pagination")
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_nullable_lists_and_pagination(cls, data: Any) -> Any:
        """Coerce null topics/reviews to empty lists and unify the serpapi_pagination key."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if normalized.get("topics") is None:
            normalized["topics"] = []
        if normalized.get("reviews") is None:
            normalized["reviews"] = []
        if normalized.get("pagination") is None and normalized.get("serpapi_pagination") is not None:
            normalized["pagination"] = normalized["serpapi_pagination"]
        return normalized
