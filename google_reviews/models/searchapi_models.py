"""Spec-aligned Pydantic models for SearchAPI Maps, Maps Place, and Maps Reviews."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SearchApiMapsPlaceParams(BaseModel):
    """Parameters for SearchAPI Google Maps Place endpoint."""

    place_id: str | None = None
    data_id: str | None = None
    hl: str | None = None
    gl: str | None = None
    zero_retention: bool | None = None

    @model_validator(mode="after")
    def validate_ids(self) -> SearchApiMapsPlaceParams:
        """Require at least one of place_id or data_id."""
        if not self.place_id and not self.data_id:
            raise ValueError("Either place_id or data_id must be provided.")

        return self

    def to_query_params(self) -> dict[str, Any]:
        """Serialise non-None fields and inject the engine key."""
        query_params = self.model_dump(exclude_none=True)
        query_params["engine"] = "google_maps_place"
        return query_params


class SearchApiMapsParams(BaseModel):
    """Parameters for SearchAPI Google Maps endpoint."""

    q: str
    ll: str | None = None
    hl: str | None = None
    gl: str | None = None
    page: int | None = Field(default=None, ge=1)
    zero_retention: bool | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Serialise non-None fields and inject the engine key."""
        query_params = self.model_dump(exclude_none=True)
        query_params["engine"] = "google_maps"
        return query_params


class SearchApiMapsReviewsParams(BaseModel):
    """Parameters for SearchAPI Google Maps Reviews endpoint."""

    place_id: str | None = None
    data_id: str | None = None
    hl: str | None = None
    gl: str | None = None
    search_query: str | None = None
    topic_id: str | None = None
    sort_by: Literal["most_relevant", "newest", "highest_rating", "lowest_rating"] | None = None
    num: int | None = Field(default=None, ge=1, le=20)
    next_page_token: str | None = None
    zero_retention: bool | None = None

    @model_validator(mode="after")
    def validate_ids(self) -> SearchApiMapsReviewsParams:
        """Require at least one of place_id or data_id."""
        if not self.place_id and not self.data_id:
            raise ValueError("Either place_id or data_id must be provided.")

        return self

    def to_query_params(self) -> dict[str, Any]:
        """Serialise non-None fields and inject the engine key."""
        query_params = self.model_dump(exclude_none=True)
        query_params["engine"] = "google_maps_reviews"
        return query_params


class SearchApiSearchMetadata(BaseModel):
    """Common SearchAPI search metadata payload."""

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


class SearchApiRatingHistogram(BaseModel):
    """Ratings histogram object with star buckets from 1 to 5."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    one_star: int | None = Field(default=None, alias="1")
    two_star: int | None = Field(default=None, alias="2")
    three_star: int | None = Field(default=None, alias="3")
    four_star: int | None = Field(default=None, alias="4")
    five_star: int | None = Field(default=None, alias="5")


class SearchApiGpsCoordinates(BaseModel):
    """Latitude and longitude coordinates."""

    model_config = ConfigDict(extra="allow")

    latitude: float | None = None
    longitude: float | None = None


class SearchApiPost(BaseModel):
    """Post entry included in maps/maps place payloads."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    source: str | None = None
    link: str | None = None


class SearchApiReservationLink(BaseModel):
    """Reservation link entry."""

    model_config = ConfigDict(extra="allow")

    text: str | None = None
    link: str | None = None


class SearchApiExtensionItem(BaseModel):
    """Extension item with title/value pair."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    value: str | None = None


class SearchApiExtension(BaseModel):
    """Extension section for additional place data."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    items: list[SearchApiExtensionItem] = Field(default_factory=list)


class SearchApiPlaceImage(BaseModel):
    """Image entry with title and thumbnail URL."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    thumbnail: str | None = None


class SearchApiPopularTimesChartEntry(BaseModel):
    """Single time bucket in popular times chart."""

    model_config = ConfigDict(extra="allow")

    time: str | None = None
    busyness_score: int | None = None
    info: str | None = None


class SearchApiPopularTimesLive(BaseModel):
    """Current live busyness details."""

    model_config = ConfigDict(extra="allow")

    info: str | None = None
    typical_time_spent: str | None = None


class SearchApiPopularTimes(BaseModel):
    """Popular times section for place payloads."""

    model_config = ConfigDict(extra="allow")

    live: SearchApiPopularTimesLive | None = None
    chart: dict[str, list[SearchApiPopularTimesChartEntry]] = Field(default_factory=dict)


class SearchApiPricingOffer(BaseModel):
    """One pricing option in place details."""

    model_config = ConfigDict(extra="allow")

    source: str | None = None
    price: str | None = None
    extracted_price: float | None = None
    price_with_taxes: str | None = None
    extracted_price_with_taxes: float | None = None
    tracking_link: str | None = None
    highlights: list[str] = Field(default_factory=list)


class SearchApiPricingOffers(BaseModel):
    """Grouped pricing options."""

    model_config = ConfigDict(extra="allow")

    featured_options: list[SearchApiPricingOffer] = Field(default_factory=list)
    all_options: list[SearchApiPricingOffer] = Field(default_factory=list)


class SearchApiPricing(BaseModel):
    """Pricing summary."""

    model_config = ConfigDict(extra="allow")

    start_date: str | None = None
    end_date: str | None = None
    offers: SearchApiPricingOffers | None = None


class SearchApiReservation(BaseModel):
    """Reservation metadata."""

    model_config = ConfigDict(extra="allow")

    link: str | None = None
    source: str | None = None


class SearchApiMenu(BaseModel):
    """Menu metadata."""

    model_config = ConfigDict(extra="allow")

    link: str | None = None
    source: str | None = None


class SearchApiWeatherTemperature(BaseModel):
    """Temperature object for weather block."""

    model_config = ConfigDict(extra="allow")

    fahrenheit: int | None = None
    celsius: int | None = None


class SearchApiWeather(BaseModel):
    """Weather details."""

    model_config = ConfigDict(extra="allow")

    temperature: SearchApiWeatherTemperature | None = None
    conditions: str | None = None


class SearchApiPlaceReview(BaseModel):
    """Place review object used in place review_results."""

    model_config = ConfigDict(extra="allow")

    username: str | None = None
    rating: float | None = None
    contributor_id: str | None = None
    description: str | None = None
    link: str | None = None
    date: str | None = None
    images: list[str] = Field(default_factory=list)


class SearchApiWebReviewResult(BaseModel):
    """Single external web review entry."""

    model_config = ConfigDict(extra="allow")

    username: str | None = None
    link: str | None = None
    rating: int | None = None
    description: str | None = None
    date: str | None = None


class SearchApiWebReview(BaseModel):
    """External review source block."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    rating: float | None = None
    reviews: int | None = None
    review_results: list[SearchApiWebReviewResult] = Field(default_factory=list)


class SearchApiHotelSummaryDimension(BaseModel):
    """Single hotel summary dimension."""

    model_config = ConfigDict(extra="allow")

    rating: float | None = None
    text: str | None = None


class SearchApiHotelSummary(BaseModel):
    """Hotel summary ratings section."""

    model_config = ConfigDict(extra="allow")

    rooms: SearchApiHotelSummaryDimension | None = None
    location: SearchApiHotelSummaryDimension | None = None
    service_and_facilities: SearchApiHotelSummaryDimension | None = None


class SearchApiReviewResults(BaseModel):
    """Review results block in place details."""

    model_config = ConfigDict(extra="allow")

    hotel_summary: SearchApiHotelSummary | None = None
    summaries: list[str] = Field(default_factory=list)
    reviews: list[SearchApiPlaceReview] = Field(default_factory=list)
    web_reviews: list[SearchApiWebReview] = Field(default_factory=list)


class SearchApiMapsPlaceResult(BaseModel):
    """Google Maps Place schema from the place OpenAPI spec."""

    model_config = ConfigDict(extra="allow")

    ludocid: str | None = None
    place_id: str | None = None
    kgmid: str | None = None
    data_id: str | None = None
    title: str | None = None
    description: str | None = None
    weather: SearchApiWeather | None = None
    features: str | None = None
    address: str | None = None
    located_in: str | None = None
    is_entity_closed: bool | None = None
    operational_status: str | None = None
    phone: str | None = None
    plus_code: str | None = None
    price: str | None = None
    price_description: str | None = None
    hotel_stars: str | None = None
    rating: float | None = None
    reviews: int | None = None
    reviews_histogram: SearchApiRatingHistogram | None = None
    reviews_link: str | None = None
    pricing: SearchApiPricing | None = None
    is_unclaimed_listing: bool | None = None
    website: str | None = None
    domain: str | None = None
    gps_coordinates: SearchApiGpsCoordinates | None = None
    type: str | None = None
    types: list[str] = Field(default_factory=list)
    reservation: SearchApiReservation | None = None
    menu: SearchApiMenu | None = None
    amenities: list[str] = Field(default_factory=list)
    open_state: str | None = None
    hours: str | None = None
    open_hours: dict[str, str] = Field(default_factory=dict)
    reservation_links: list[SearchApiReservationLink] = Field(default_factory=list)
    booking_link: str | None = None
    thumbnail: str | None = None
    images: list[SearchApiPlaceImage] = Field(default_factory=list)
    extensions: list[SearchApiExtension] = Field(default_factory=list)
    posts: list[SearchApiPost] = Field(default_factory=list)
    admissions: list[dict[str, Any]] = Field(default_factory=list)
    experiences: list[dict[str, Any]] = Field(default_factory=list)
    questions_and_answers: dict[str, Any] | None = None
    at_this_place: list[dict[str, Any]] | dict[str, Any] | None = None
    hotels_nearby: list[dict[str, Any]] = Field(default_factory=list)
    review_results: SearchApiReviewResults | None = None
    similar_places_nearby: list[dict[str, Any]] = Field(default_factory=list)
    similar_rentals_nearby: list[dict[str, Any]] = Field(default_factory=list)
    people_also_search_for: list[dict[str, Any]] = Field(default_factory=list)
    popular_times: SearchApiPopularTimes | None = None


class SearchApiMapsPlaceSearchParameters(BaseModel):
    """Google Maps Place search parameters block."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None
    place_id: str | None = None
    data_id: str | None = None
    hl: str | None = None
    gl: str | None = None


class SearchApiMapsPlaceResponse(BaseModel):
    """Typed response envelope for Google Maps Place search."""

    model_config = ConfigDict(extra="allow")

    search_metadata: SearchApiSearchMetadata | None = None
    search_parameters: SearchApiMapsPlaceSearchParameters | None = None
    place_result: SearchApiMapsPlaceResult | None = None
    error: str | None = None


class SearchApiMapsSearchParameters(BaseModel):
    """Google Maps search parameters block."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None
    q: str | None = None
    ll: str | None = None
    hl: str | None = None
    gl: str | None = None
    page: int | None = None


class SearchApiMapsSearchInformation(BaseModel):
    """Google Maps search information block."""

    model_config = ConfigDict(extra="allow")

    query_displayed: str | None = None
    did_you_mean: str | None = None
    state: (
        Literal[
            "Showing results for fixed spelling.",
            "Showing results for exact spelling.",
            "Showing results for original spelling.",
        ]
        | None
    ) = None


class SearchApiMapsLocalResult(BaseModel):
    """Local result schema from Google Maps search OpenAPI."""

    model_config = ConfigDict(extra="allow")

    position: int | None = None
    ludocid: str | None = None
    place_id: str | None = None
    kgmid: str | None = None
    data_id: str | None = None
    title: str | None = None
    description: str | None = None
    features: list[str] = Field(default_factory=list)
    address: str | None = None
    phone: str | None = None
    price: str | None = None
    price_description: str | None = None
    hotel_stars: int | None = None
    rating: float | None = None
    reviews: int | None = None
    reviews_link: str | None = None
    review_text: str | None = None
    is_unclaimed_listing: bool | None = None
    website: str | None = None
    domain: str | None = None
    gps_coordinates: SearchApiGpsCoordinates | None = None
    type: str | None = None
    types: list[str] = Field(default_factory=list)
    tracking_title: str | None = None
    tracking_link: str | None = None
    posts: list[SearchApiPost] = Field(default_factory=list)
    amenities: list[str] = Field(default_factory=list)
    open_state: str | None = None
    hours: str | None = None
    open_hours: dict[str, str] = Field(default_factory=dict)
    reservation_links: list[SearchApiReservationLink] = Field(default_factory=list)
    extensions: list[SearchApiExtension] = Field(default_factory=list)
    images: list[str | SearchApiPlaceImage] = Field(default_factory=list)
    thumbnail: str | None = None


class SearchApiMapsAd(SearchApiMapsLocalResult):
    """Sponsored map ad result (extends local result with tracking fields)."""


class SearchApiMapsResponse(BaseModel):
    """Typed response envelope for Google Maps search."""

    model_config = ConfigDict(extra="allow")

    search_metadata: SearchApiSearchMetadata | None = None
    search_parameters: SearchApiMapsSearchParameters | None = None
    search_information: SearchApiMapsSearchInformation | None = None
    ads: list[SearchApiMapsAd] = Field(default_factory=list)
    local_results: list[SearchApiMapsLocalResult] = Field(default_factory=list)
    error: str | None = None


class SearchApiMapsReviewsSearchParameters(BaseModel):
    """Google Maps Reviews search parameters block."""

    model_config = ConfigDict(extra="allow")

    engine: str | None = None
    data_id: str | None = None
    place_id: str | None = None
    search_query: str | None = None
    topic_id: str | None = None
    sort_by: str | None = None
    hl: str | None = None
    gl: str | None = None
    num: int | None = None
    next_page_token: str | None = None


class SearchApiMapsReviewsPlaceResult(BaseModel):
    """Place summary object in reviews response."""

    model_config = ConfigDict(extra="allow")

    title: str | None = None
    address: str | None = None
    phone: str | None = None
    rating: float | None = None
    reviews: int | None = None
    reviews_histogram: SearchApiRatingHistogram | None = None
    type: str | None = None


class SearchApiMapsReviewTopic(BaseModel):
    """Topic aggregation in reviews response."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    keyword: str | None = None
    reviews: int | None = None


class SearchApiMapsReviewUser(BaseModel):
    """Review author payload."""

    model_config = ConfigDict(extra="allow")

    name: str | None = None
    link: str | None = None
    contributor_id: str | None = None
    is_local_guide: bool | None = None
    reviews: int | None = None
    photos: int | None = None
    thumbnail: str | None = None


class SearchApiMapsReviewImage(BaseModel):
    """Review image payload."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    image: str | None = None


class SearchApiMapsReviewResponse(BaseModel):
    """Business response attached to a review."""

    model_config = ConfigDict(extra="allow")

    date: str | None = None
    iso_date: str | None = None
    text: str | None = None
    translated_text: str | None = None


class SearchApiMapsReview(BaseModel):
    """Reviews entry from Google Maps Reviews endpoint."""

    model_config = ConfigDict(extra="allow")

    review_id: str | None = None
    user: SearchApiMapsReviewUser | None = None
    link: str | None = None
    source: str | None = None
    text: str | None = None
    translated_text: str | None = None
    rating: int | None = None
    rating_details: dict[str, Any] | None = None
    date: str | None = None
    iso_date: str | None = None
    likes: int | None = None
    images: list[SearchApiMapsReviewImage] = Field(default_factory=list)
    response: SearchApiMapsReviewResponse | None = None


class SearchApiMapsReviewsPagination(BaseModel):
    """Pagination object for reviews endpoint."""

    model_config = ConfigDict(extra="allow")

    next_page_token: str | None = None


class SearchApiMapsReviewsResponse(BaseModel):
    """Typed response envelope for Google Maps Reviews search."""

    model_config = ConfigDict(extra="allow")

    search_metadata: SearchApiSearchMetadata | None = None
    search_parameters: SearchApiMapsReviewsSearchParameters | None = None
    place_result: SearchApiMapsReviewsPlaceResult | None = None
    topics: list[SearchApiMapsReviewTopic] = Field(default_factory=list)
    reviews: list[SearchApiMapsReview] = Field(default_factory=list)
    pagination: SearchApiMapsReviewsPagination | None = None
    error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_nullable_lists(cls, data: Any) -> Any:
        """Coerce null topics and reviews fields to empty lists before Pydantic validation."""
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        if normalized.get("topics") is None:
            normalized["topics"] = []
        if normalized.get("reviews") is None:
            normalized["reviews"] = []
        return normalized
