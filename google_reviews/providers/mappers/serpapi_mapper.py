"""SerpAPI payload to domain model mappers."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

from ...models.domain_models import (
    DiscoveredPlace,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
)
from ...models.serpapi_models import (
    SerpApiMapsLocalResult,
    SerpApiMapsResponse,
    SerpApiMapsReview,
    SerpApiMapsReviewsResponse,
)

SerpApiReviewsSortBy = Literal["qualityScore", "newestFirst", "ratingHigh", "ratingLow"]


def map_sort_order_to_serpapi_value(sort_order: ReviewSortOrder) -> SerpApiReviewsSortBy:
    """Map canonical sort labels to SerpAPI's `sort_by` vocabulary."""

    if sort_order == ReviewSortOrder.newest:
        return "newestFirst"
    if sort_order == ReviewSortOrder.best:
        return "ratingHigh"
    if sort_order == ReviewSortOrder.worst:
        return "ratingLow"
    if sort_order == ReviewSortOrder.most_relevant:
        return "qualityScore"
    raise ValueError(f"Unsupported sort_order for SerpAPI sort_by mapping: `{sort_order.value}`")


def map_maps_response_to_discovered_places(
    *,
    response: SerpApiMapsResponse,
    company_website_url: str,
    provider_name: str,
    scraped_at: datetime,
) -> list[DiscoveredPlace]:
    """Convert SerpAPI maps response local results into canonical place models."""

    unique_by_place_id: dict[str, DiscoveredPlace] = {}
    for local_result in response.local_results:
        mapped_place = _map_local_result_to_discovered_place(
            local_result=local_result,
            company_website_url=company_website_url,
            provider_name=provider_name,
            scraped_at=scraped_at,
        )
        if mapped_place is None:
            continue
        if mapped_place.place_id not in unique_by_place_id:
            unique_by_place_id[mapped_place.place_id] = mapped_place

    return list(unique_by_place_id.values())


def map_reviews_response_to_review_records(
    *,
    response: SerpApiMapsReviewsResponse,
    place: DiscoveredPlace,
    sort_order: ReviewSortOrder = ReviewSortOrder.unspecified,
    scraped_at: datetime,
    rank_offset: int = 0,
) -> list[ReviewRecord]:
    """Map SerpAPI reviews payload into canonical review records preserving response order."""

    review_records: list[ReviewRecord] = []
    for index, review in enumerate(response.reviews, start=rank_offset + 1):
        review_records.append(
            _map_review_to_record(
                review=review,
                place=place,
                sort_order=sort_order,
                sort_rank=index,
                scraped_at=scraped_at,
            )
        )
    return review_records


def map_reviews_response_to_review_histogram(
    *,
    response: SerpApiMapsReviewsResponse,
    place: DiscoveredPlace,
    scraped_at: datetime,
) -> ReviewHistogram | None:
    """Extract review histogram block from SerpAPI reviews response."""

    place_result = response.place_result or response.place_info
    if place_result is None:
        return None

    if place_result.reviews_histogram is not None:
        histogram = place_result.reviews_histogram
        return ReviewHistogram(
            provider=place.provider,
            place_id=place.place_id,
            data_id=place.data_id,
            star_1=histogram.one_star or 0,
            star_2=histogram.two_star or 0,
            star_3=histogram.three_star or 0,
            star_4=histogram.four_star or 0,
            star_5=histogram.five_star or 0,
            total_reviews=place_result.reviews,
            scraped_at=scraped_at,
            raw_payload=response.model_dump(mode="json", exclude_none=False),
        )

    if not place_result.rating_summary:
        return None

    stars: dict[int, int] = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for row in place_result.rating_summary:
        if row.stars in stars:
            stars[row.stars] = row.amount or 0

    return ReviewHistogram(
        provider=place.provider,
        place_id=place.place_id,
        data_id=place.data_id,
        star_1=stars[1],
        star_2=stars[2],
        star_3=stars[3],
        star_4=stars[4],
        star_5=stars[5],
        total_reviews=place_result.reviews,
        scraped_at=scraped_at,
        raw_payload=response.model_dump(mode="json", exclude_none=False),
    )


def _map_local_result_to_discovered_place(
    *,
    local_result: SerpApiMapsLocalResult,
    company_website_url: str,
    provider_name: str,
    scraped_at: datetime,
) -> DiscoveredPlace | None:
    """Convert a single SerpAPI local result to a DiscoveredPlace, or None if place_id is absent."""
    place_id = local_result.place_id
    if not place_id:
        return None

    website_domain = _normalize_domain(local_result.domain)
    if website_domain is None:
        website_domain = _normalize_domain(local_result.website)
    if website_domain is None and local_result.links is not None:
        website_domain = _normalize_domain(local_result.links.website)

    return DiscoveredPlace(
        provider=provider_name,
        place_id=place_id,
        data_id=local_result.data_id,
        company_website_url=company_website_url,
        name=local_result.title,
        address=local_result.address,
        website_domain=website_domain,
        rating=local_result.rating,
        reviews_count=local_result.reviews,
        scraped_at=scraped_at,
        raw_payload=local_result.model_dump(mode="json", exclude_none=False),
    )


def _map_review_to_record(
    *,
    review: SerpApiMapsReview,
    place: DiscoveredPlace,
    sort_order: ReviewSortOrder,
    sort_rank: int,
    scraped_at: datetime,
) -> ReviewRecord:
    """Convert a SerpAPI review object to a canonical ReviewRecord."""
    review_id = _resolve_review_id(review=review, place=place, sort_order=sort_order, sort_rank=sort_rank)
    return ReviewRecord(
        provider=place.provider,
        place_id=place.place_id,
        data_id=place.data_id,
        review_id=review_id,
        sort_order=sort_order,
        sort_rank=sort_rank,
        author_name=review.user.name if review.user else None,
        author_contributor_id=review.user.contributor_id if review.user else None,
        rating=review.rating,
        text=review.text or review.snippet,
        translated_text=review.translated_text,
        likes=review.likes,
        written_at=_parse_datetime(review.iso_date) or _parse_datetime(review.date),
        source=review.source,
        review_link=review.link,
        scraped_at=scraped_at,
        raw_payload=review.model_dump(mode="json", exclude_none=False),
    )


def _resolve_review_id(
    *,
    review: SerpApiMapsReview,
    place: DiscoveredPlace,
    sort_order: ReviewSortOrder,
    sort_rank: int,
) -> str:
    """Return provider review_id or id if present; otherwise synthesise a stable SHA-256-based ID."""
    if review.review_id:
        return review.review_id
    if review.id:
        return review.id

    digest_source = "|".join(
        [
            place.provider,
            place.place_id,
            sort_order.value,
            str(sort_rank),
            review.link or "",
            review.iso_date or review.date or "",
            str(review.rating or ""),
            (review.text or review.snippet or "")[:256],
        ]
    )
    digest = hashlib.sha256(digest_source.encode("utf-8")).hexdigest()
    return f"synthetic_{digest[:24]}"


def _parse_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 string to a UTC-aware datetime, returning None on missing or malformed input."""
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _normalize_domain(value: str | None) -> str | None:
    """Extract and normalise the bare hostname from a URL or domain string, stripping leading www."""
    if not value:
        return None

    candidate = value.strip().lower()
    if not candidate:
        return None

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if not parsed.hostname:
        return None

    normalized = parsed.hostname.lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized
