"""MCP-ready service orchestration for company review workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from ..exceptions import PlaceNotFoundError
from ..logging_config import get_logger
from ..models.domain_models import (
    CompanyRecord,
    DiscoveredPlace,
    LocationOverview,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
)
from ..providers.base_provider import MapsProvider
from ..storage.base_repository import ReviewsRepository

logger = get_logger(__name__)

_ALL_SORT_ORDERS = [
    ReviewSortOrder.best,
    ReviewSortOrder.worst,
    ReviewSortOrder.newest,
    ReviewSortOrder.most_relevant,
]


class CompanyReviewService:
    """MCP-ready service for company Google Maps review workflows.

    Provider and repository are injected at construction time.  Public methods
    expose only business parameters suitable for MCP tool schemas.
    """

    def __init__(self, *, provider: MapsProvider, repository: ReviewsRepository) -> None:
        """Store the injected provider and repository."""
        self._provider = provider
        self._repository = repository

    def close(self) -> None:
        """Release resources held by the service (delegates to the repository)."""
        self._repository.close()

    # ------------------------------------------------------------------
    # Public MCP tool methods
    # ------------------------------------------------------------------

    def search_company_places(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
    ) -> str:
        """Discover Google Maps places matching a company website URL.

        Returns cached results if available, otherwise queries the Maps API
        with fallback search strategies: domain -> company name -> bare name.
        """
        places = self._search_company_places_core(
            company_url=company_url,
            company_name=company_name,
        )
        return _format_places(places)

    def get_place_reviews(
        self,
        *,
        data_id: str,
        num_reviews: int = 20,
        sort_order: str | None = None,
    ) -> str:
        """Fetch reviews for a specific place by data_id.

        The place must have been previously discovered via search_company_places.
        Returns cached reviews if sufficient, otherwise queries the API.
        """
        place, reviews, histogram = self._get_place_reviews_core(
            data_id=data_id,
            num_reviews=num_reviews,
            sort_order=sort_order,
        )
        return _format_reviews_and_histogram(reviews, histogram, place=place)

    def get_company_overview(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
        max_companies: int = 3,
        max_reviews_per_sort: int = 20,
    ) -> str:
        """Full company review overview across all locations and sort orders.

        Discovers places, fetches reviews (best, worst, newest, most_relevant),
        and retrieves histograms for each location.
        """
        canonical_url, locations, skipped_places = self._get_company_overview_core(
            company_url=company_url,
            company_name=company_name,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
        )

        sections: list[str] = []
        for place, reviews_by_sort, histogram in locations:
            place_parts: list[str] = [_format_single_place(place)]

            for sort_label, reviews in reviews_by_sort.items():
                if reviews:
                    place_parts.append(f"\n[{sort_label} reviews]")
                    place_parts.append(_format_review_list(reviews))

            if histogram is not None:
                place_parts.append(_format_histogram(histogram))

            sections.append("\n".join(place_parts))

        if skipped_places:
            sections.append(_format_skipped_places(skipped_places))

        return "\n\n===\n\n".join(sections) if sections else "No places found."

    # ------------------------------------------------------------------
    # Public MCP tool methods - structured (raw JSON) output
    # ------------------------------------------------------------------

    def search_company_places_raw(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
    ) -> dict[str, Any]:
        """Discover Google Maps places and return structured place data.

        Same orchestration as search_company_places but returns a dict with
        the raw provider payload instead of a formatted string.
        """
        places = self._search_company_places_core(
            company_url=company_url,
            company_name=company_name,
        )
        return _places_to_raw(places)

    def get_place_reviews_raw(
        self,
        *,
        data_id: str,
        num_reviews: int = 20,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Fetch reviews for a place and return structured data.

        Returns a dict containing raw provider payloads for place, reviews,
        and histogram (if available).
        """
        place, reviews, histogram = self._get_place_reviews_core(
            data_id=data_id,
            num_reviews=num_reviews,
            sort_order=sort_order,
        )
        return _place_reviews_to_raw(place, reviews, histogram)

    def get_company_overview_raw(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
        max_companies: int = 3,
        max_reviews_per_sort: int = 20,
    ) -> dict[str, Any]:
        """Full company review overview returned as structured data.

        Same orchestration as get_company_overview but returns a dict
        with raw provider payloads for places, reviews, and histograms.
        """
        canonical_url, locations, skipped_places = self._get_company_overview_core(
            company_url=company_url,
            company_name=company_name,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
        )
        _, normalized_domain = normalize_company_url(company_url)

        locations_raw: list[dict[str, Any]] = []
        for place, reviews_by_sort, histogram in locations:
            reviews_raw: dict[str, list[dict[str, Any]]] = {
                label: [r.raw_payload for r in revs]
                for label, revs in reviews_by_sort.items()
                if revs
            }
            location_entry: dict[str, Any] = {
                "place": place.raw_payload,
                "reviews": reviews_raw,
            }
            if histogram is not None:
                location_entry["histogram"] = histogram.raw_payload
            locations_raw.append(location_entry)

        return {
            "company_website_url": canonical_url,
            "normalized_website_domain": normalized_domain,
            "locations": locations_raw,
            "additional_locations": [p.raw_payload for p in skipped_places],
        }

    # ------------------------------------------------------------------
    # Internal orchestration helpers
    # ------------------------------------------------------------------

    def _search_company_places_core(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
    ) -> list[DiscoveredPlace]:
        """Shared orchestration for search_company_places / search_company_places_raw."""
        canonical_url, normalized_domain = normalize_company_url(company_url)
        logger.info("search_company_places started company_url=%s", canonical_url)

        places, _ = self._ensure_places_and_run(
            canonical_url=canonical_url,
            normalized_domain=normalized_domain,
            company_name=company_name,
            scraped_at=datetime.now(tz=UTC),
        )

        logger.info(
            "search_company_places finished company_url=%s places=%s",
            canonical_url,
            len(places),
        )
        return places

    def _get_place_reviews_core(
        self,
        *,
        data_id: str,
        num_reviews: int = 20,
        sort_order: str | None = None,
    ) -> tuple[DiscoveredPlace, list[ReviewRecord], ReviewHistogram | None]:
        """Shared orchestration for get_place_reviews / get_place_reviews_raw."""
        place = self._repository.get_current_place_by_data_id(data_id=data_id)
        if place is None:
            raise PlaceNotFoundError(data_id=data_id)

        resolved_sort = _resolve_sort_order(sort_order)
        current_run = self._repository.get_current_scrape_run(
            company_website_url=place.company_website_url,
        )
        if current_run is None:
            raise PlaceNotFoundError(data_id=data_id)

        logger.info(
            "get_place_reviews started data_id=%s sort=%s num=%s",
            data_id,
            resolved_sort.value,
            num_reviews,
        )

        scraped_at = datetime.now(tz=UTC)
        reviews = self._ensure_reviews_for_place(
            place=place,
            sort_order=resolved_sort,
            num_reviews=num_reviews,
            scrape_run_id=current_run.scrape_run_id,
            scraped_at=scraped_at,
        )
        histogram = self._ensure_histogram_for_place(
            place=place,
            scrape_run_id=current_run.scrape_run_id,
            scraped_at=scraped_at,
        )

        return place, reviews, histogram

    def _get_company_overview_core(
        self,
        *,
        company_url: str,
        company_name: str | None = None,
        max_companies: int = 3,
        max_reviews_per_sort: int = 20,
    ) -> tuple[
        str,
        list[tuple[DiscoveredPlace, dict[str, list[ReviewRecord]], ReviewHistogram | None]],
        list[DiscoveredPlace],
    ]:
        """Shared orchestration for get_company_overview / get_company_overview_raw.

        Returns (canonical_url, locations, skipped_places) where each location is a tuple of
        (place, reviews_by_sort_label, histogram) and skipped_places are discovered locations
        beyond max_companies for which reviews were not fetched.
        """
        max_reviews_per_sort = min(max_reviews_per_sort, 48)
        canonical_url, normalized_domain = normalize_company_url(company_url)
        logger.info(
            "get_company_overview started company_url=%s max_companies=%s max_reviews=%s",
            canonical_url,
            max_companies,
            max_reviews_per_sort,
        )

        scraped_at = datetime.now(tz=UTC)
        all_places, scrape_run_id = self._ensure_places_and_run(
            canonical_url=canonical_url,
            normalized_domain=normalized_domain,
            company_name=company_name,
            scraped_at=scraped_at,
        )
        places = all_places[:max_companies]
        skipped_places = all_places[max_companies:]

        locations: list[tuple[DiscoveredPlace, dict[str, list[ReviewRecord]], ReviewHistogram | None]] = []
        for place in places:
            reviews_by_sort: dict[str, list[ReviewRecord]] = {}
            if place.reviews_count is not None and place.reviews_count <= 4 * max_reviews_per_sort:
                reviews = self._ensure_reviews_for_place(
                    place=place,
                    sort_order=ReviewSortOrder.most_relevant,
                    num_reviews=place.reviews_count,
                    scrape_run_id=scrape_run_id,
                    scraped_at=scraped_at,
                )
                if reviews:
                    reviews_by_sort["all"] = reviews
            else:
                for so in _ALL_SORT_ORDERS:
                    reviews = self._ensure_reviews_for_place(
                        place=place,
                        sort_order=so,
                        num_reviews=max_reviews_per_sort,
                        scrape_run_id=scrape_run_id,
                        scraped_at=scraped_at,
                    )
                    if reviews:
                        reviews_by_sort[so.value] = reviews

            histogram = self._ensure_histogram_for_place(
                place=place,
                scrape_run_id=scrape_run_id,
                scraped_at=scraped_at,
            )
            locations.append((place, reviews_by_sort, histogram))

        logger.info(
            "get_company_overview finished company_url=%s places=%s skipped=%s",
            canonical_url,
            len(places),
            len(skipped_places),
        )
        return canonical_url, locations, skipped_places

    def _discover_places_with_fallback(
        self,
        *,
        canonical_url: str,
        normalized_domain: str,
        company_name: str | None,
        scraped_at: datetime,
    ) -> list[DiscoveredPlace]:
        """Try multiple query strategies to discover domain-matched places."""
        queries: list[str] = [normalized_domain]
        if company_name and company_name not in queries:
            queries.append(company_name)
        bare_name = normalized_domain.split(".")[0]
        if bare_name and bare_name not in queries:
            queries.append(bare_name)

        for query in queries:
            logger.info("discover_places trying query=%s", query)
            discovered = self._provider.discover_company_places(query=query)
            filtered = _filter_places_by_company_domain(
                places=discovered,
                company_website_url=canonical_url,
                normalized_company_domain=normalized_domain,
                scraped_at=scraped_at,
            )
            if filtered:
                return filtered

        return []

    def _ensure_places_and_run(
        self,
        *,
        canonical_url: str,
        normalized_domain: str,
        company_name: str | None,
        scraped_at: datetime,
    ) -> tuple[list[DiscoveredPlace], str]:
        """Return (places, scrape_run_id), creating a run if none exists."""
        current_run = self._repository.get_current_scrape_run(company_website_url=canonical_url)
        if current_run is not None:
            overview = self._repository.get_current_company_overview(
                company_website_url=canonical_url,
                limit_per_sort=1,
                include_most_relevant=False,
            )
            if overview is not None and overview.locations:
                places = [
                    _location_to_discovered_place(loc, canonical_url, current_run.scraped_at)
                    for loc in overview.locations
                ]
                return places, current_run.scrape_run_id

        filtered_places = self._discover_places_with_fallback(
            canonical_url=canonical_url,
            normalized_domain=normalized_domain,
            company_name=company_name,
            scraped_at=scraped_at,
        )
        company = CompanyRecord(
            company_website_url=canonical_url,
            normalized_website_domain=normalized_domain,
            scraped_at=scraped_at,
            raw_payload=_build_discovery_metadata(
                provider_name=self._provider.provider_name,
                query=normalized_domain,
                places=filtered_places,
            ),
        )
        with self._repository.transaction():
            self._repository.upsert_company(company)
            run = self._repository.start_scrape_run(
                company_website_url=canonical_url,
                include_most_relevant=True,
                requested_limit_per_sort=20,
                scraped_at=scraped_at,
            )
            self._repository.replace_run_places(
                scrape_run_id=run.scrape_run_id,
                places=filtered_places,
            )
            self._repository.set_scrape_run_current(
                company_website_url=canonical_url,
                scrape_run_id=run.scrape_run_id,
            )

        return filtered_places, run.scrape_run_id

    def _ensure_reviews_for_place(
        self,
        *,
        place: DiscoveredPlace,
        sort_order: ReviewSortOrder,
        num_reviews: int,
        scrape_run_id: str,
        scraped_at: datetime,
    ) -> list[ReviewRecord]:
        """Return cached reviews or fetch from provider and upsert."""
        if num_reviews == -1:
            num_reviews = self._provider.max_reviews_fetch_cap
        if num_reviews == 0:
            return []
        if num_reviews < 1:
            raise ValueError(f"num_reviews must be -1 or >= 1, got {num_reviews!r}")
        cached = self._repository.get_reviews_for_place_sort(
            scrape_run_id=scrape_run_id,
            provider=place.provider,
            place_id=place.place_id,
            sort_order=sort_order,
            limit=num_reviews,
        )
        place_total = place.reviews_count
        cache_satisfies_request = len(cached) >= num_reviews
        cache_exhausted = place_total is not None and len(cached) >= place_total
        if cache_satisfies_request or cache_exhausted:
            logger.info(
                "reviews cache_hit place_id=%s sort=%s cached=%s requested=%s total=%s",
                place.place_id,
                sort_order.value,
                len(cached),
                num_reviews,
                place_total,
            )
            return cached

        fetched = self._provider.retrieve_num_reviews(
            place=place,
            sort_order=sort_order,
            num=num_reviews,
        )
        stamped = [r.model_copy(update={"scraped_at": scraped_at}) for r in fetched]
        if stamped:
            self._repository.upsert_run_reviews(scrape_run_id=scrape_run_id, reviews=stamped)

        return stamped

    def _ensure_histogram_for_place(
        self,
        *,
        place: DiscoveredPlace,
        scrape_run_id: str,
        scraped_at: datetime,
    ) -> ReviewHistogram | None:
        """Return cached histogram or fetch from provider and upsert."""
        cached = self._repository.get_histogram_for_place(
            scrape_run_id=scrape_run_id,
            provider=place.provider,
            place_id=place.place_id,
        )
        if cached is not None:
            return cached

        histogram = self._provider.retrieve_review_histogram(place=place)
        if histogram is not None:
            stamped = histogram.model_copy(update={"scraped_at": scraped_at})
            self._repository.upsert_run_histogram(scrape_run_id=scrape_run_id, histogram=stamped)
            return stamped

        return None


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def normalize_company_url(company_url: str) -> tuple[str, str]:
    """Normalize a URL into canonical company identity URL and normalized domain."""
    candidate = company_url.strip()
    if not candidate:
        raise ValueError("company_url must not be empty.")

    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"Unable to normalize company URL: `{company_url}`")

    normalized_domain = hostname.lower()
    if normalized_domain.startswith("www."):
        normalized_domain = normalized_domain[4:]

    canonical_company_url = f"https://{normalized_domain}"
    return canonical_company_url, normalized_domain


def _filter_places_by_company_domain(
    *,
    places: list[DiscoveredPlace],
    company_website_url: str,
    normalized_company_domain: str,
    scraped_at: datetime,
) -> list[DiscoveredPlace]:
    """Keep only places whose website_domain matches the company domain, rebinding company_website_url."""
    filtered_places: list[DiscoveredPlace] = []
    for place in places:
        if not _domain_match_only(place_domain=place.website_domain, company_domain=normalized_company_domain):
            continue

        filtered_places.append(
            place.model_copy(
                update={
                    "company_website_url": company_website_url,
                    "scraped_at": scraped_at,
                }
            )
        )

    return filtered_places


def _domain_match_only(*, place_domain: str | None, company_domain: str) -> bool:
    """Return True if place_domain equals or is a subdomain of company_domain."""
    if not place_domain:
        return False

    normalized_place_domain = place_domain.lower().strip()
    if normalized_place_domain.startswith("www."):
        normalized_place_domain = normalized_place_domain[4:]

    return normalized_place_domain == company_domain or normalized_place_domain.endswith(f".{company_domain}")


def _resolve_sort_order(sort_order: str | None) -> ReviewSortOrder:
    """Parse a string sort_order label to ReviewSortOrder, defaulting to most_relevant."""
    if sort_order is None:
        return ReviewSortOrder.most_relevant
    try:
        return ReviewSortOrder(sort_order)
    except ValueError as err:
        valid = ", ".join(s.value for s in ReviewSortOrder if s != ReviewSortOrder.unspecified)
        raise ValueError(f"Invalid sort_order: `{sort_order}`. Valid values: {valid}") from err


def _build_discovery_metadata(
    *,
    provider_name: str,
    query: str,
    places: list[DiscoveredPlace],
) -> dict[str, Any]:
    """Lightweight discovery summary stored as CompanyRecord raw_payload."""
    return {
        "discovery_provider": provider_name,
        "discovery_query": query,
        "places_discovered": len(places),
        "place_ids": [p.place_id for p in places],
    }


def _location_to_discovered_place(
    loc: LocationOverview,
    company_website_url: str,
    scraped_at: datetime,
) -> DiscoveredPlace:
    """Rebuild a DiscoveredPlace from a LocationOverview stub for cache-hit code paths."""
    return DiscoveredPlace(
        provider=loc.provider,
        place_id=loc.place_id,
        data_id=loc.data_id,
        company_website_url=company_website_url,
        name=loc.name,
        address=loc.address,
        website_domain=loc.website_domain,
        rating=loc.rating,
        reviews_count=loc.reviews_count,
        scraped_at=scraped_at,
        raw_payload=loc.raw_payload,
    )


# ------------------------------------------------------------------
# Output formatting helpers
# ------------------------------------------------------------------


def _format_places(places: list[DiscoveredPlace]) -> str:
    """Render a list of DiscoveredPlace objects as a human-readable string."""
    if not places:
        return "No places found."
    return "\n---\n".join(_format_single_place(p) for p in places)


def _format_single_place(place: DiscoveredPlace) -> str:
    """Render a single DiscoveredPlace as a labelled block of key/value lines."""
    return "\n".join([
        "[Place]",
        f"place_id: {place.place_id}",
        f"data_id: {place.data_id}",
        f"name: {place.name}",
        f"address: {place.address}",
        f"website_domain: {place.website_domain}",
        f"rating: {place.rating}",
        f"reviews_count: {place.reviews_count}",
    ])


def _format_skipped_places(places: list[DiscoveredPlace]) -> str:
    """Render locations that were discovered but not fetched due to max_companies limit."""
    header = "[Additional locations - reviews not fetched]"
    body = "\n---\n".join(_format_single_place(p) for p in places)
    return f"{header}\n\n{body}"


def _format_reviews_and_histogram(
    reviews: list[ReviewRecord],
    histogram: ReviewHistogram | None,
    *,
    place: DiscoveredPlace | None = None,
) -> str:
    """Compose optional place info, review list, and histogram into one formatted string."""
    parts: list[str] = []

    if place is not None:
        parts.append(_format_single_place(place))

    if reviews:
        parts.append(_format_review_list(reviews))
    else:
        parts.append("No reviews found.")

    if histogram is not None:
        parts.append(_format_histogram(histogram))

    return "\n\n".join(parts)


def _format_review_list(reviews: list[ReviewRecord]) -> str:
    """Render a numbered list of ReviewRecord objects as a human-readable string."""
    formatted: list[str] = []
    for i, review in enumerate(reviews, start=1):
        lines = [
            f"[Review {i}]",
            f"review_id: {review.review_id}",
            f"sort_order: {review.sort_order.value}",
            f"sort_rank: {review.sort_rank}",
            f"author_name: {review.author_name}",
            f"rating: {review.rating}",
            f"text: {review.text}",
            f"written_at: {review.written_at.isoformat() if review.written_at else None}",
            f"likes: {review.likes}",
            f"scraped_at: {review.scraped_at.isoformat()}",
        ]
        formatted.append("\n".join(lines))
    return "\n\n".join(formatted)


def _format_histogram(histogram: ReviewHistogram) -> str:
    """Render a ReviewHistogram as a labelled block of key/value lines."""
    raw = json.dumps(histogram.raw_payload, default=str) if histogram.raw_payload else "{}"
    return "\n".join([
        "[Histogram]",
        f"star_1: {histogram.star_1}",
        f"star_2: {histogram.star_2}",
        f"star_3: {histogram.star_3}",
        f"star_4: {histogram.star_4}",
        f"star_5: {histogram.star_5}",
        f"total_reviews: {histogram.total_reviews}",
        f"scraped_at: {histogram.scraped_at.isoformat()}",
        f"raw_payload: {raw}",
    ])


# ------------------------------------------------------------------
# Raw (structured) output helpers
# ------------------------------------------------------------------


def _places_to_raw(places: list[DiscoveredPlace]) -> dict[str, Any]:
    """Return raw provider payloads for a list of places."""
    return {
        "places": [p.raw_payload for p in places],
    }


def _place_reviews_to_raw(
    place: DiscoveredPlace,
    reviews: list[ReviewRecord],
    histogram: ReviewHistogram | None,
) -> dict[str, Any]:
    """Return raw provider payloads for a place, its reviews, and optionally a histogram."""
    result: dict[str, Any] = {
        "place": place.raw_payload,
        "reviews": [r.raw_payload for r in reviews],
    }
    if histogram is not None:
        result["histogram"] = histogram.raw_payload
    return result
