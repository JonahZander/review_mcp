"""SerpAPI provider client built on top of the retrying HTTP transport wrapper."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, TypeVar

import requests
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..logging_config import get_logger
from ..models.domain_models import DiscoveredPlace, ReviewHistogram, ReviewRecord, ReviewSortOrder
from ..models.serpapi_models import (
    SerpApiMapsParams,
    SerpApiMapsResponse,
    SerpApiMapsReviewsParams,
    SerpApiMapsReviewsResponse,
)
from .base_provider import MapsProvider
from .mappers.serpapi_mapper import (
    map_maps_response_to_discovered_places,
    map_reviews_response_to_review_histogram,
    map_reviews_response_to_review_records,
    map_sort_order_to_serpapi_value,
)
from .retrying_http_client import RetryingHttpClient

SerpApiParamsModel = SerpApiMapsParams | SerpApiMapsReviewsParams

ParamsModelT = TypeVar("ParamsModelT", bound=BaseModel)
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel)
REVIEWS_PAGE_SIZE = 20

_logger = get_logger(__name__)


class SerpApiClient(MapsProvider):
    """Provider implementation for SerpAPI Maps and Maps Reviews endpoints."""

    def __init__(
        self,
        *,
        http_client: RetryingHttpClient,
        max_reviews_fetch_cap: int = 100,
        maps_no_cache: bool = False,
    ) -> None:
        """Store the HTTP client, validate the fetch cap, and set the no-cache flag."""
        if max_reviews_fetch_cap < 1:
            raise ValueError("max_reviews_fetch_cap must be >= 1")
        self._http_client = http_client
        self._max_reviews_fetch_cap = max_reviews_fetch_cap
        self._maps_no_cache = maps_no_cache
        self._histogram_cache: dict[tuple[str, str], ReviewHistogram] = {}

    @property
    def provider_name(self) -> str:
        """Return the provider identifier string."""
        return "serpapi"

    @property
    def max_reviews_fetch_cap(self) -> int:
        """Return the configured upper bound for fetch-all requests."""
        return self._max_reviews_fetch_cap

    @classmethod
    def from_settings(
        cls,
        *,
        settings: Settings | None = None,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> SerpApiClient:
        resolved_settings = settings or get_settings()
        http_client = RetryingHttpClient(
            auth_value=resolved_settings.serpapi_api_key,
            auth_query_param_name="api_key",
            service_name="serpapi",
            base_url=resolved_settings.serpapi_base_url,
            timeout_seconds=resolved_settings.http_timeout_seconds,
            retry_attempts=resolved_settings.retry_attempts,
            retry_min_seconds=resolved_settings.retry_min_seconds,
            retry_max_seconds=resolved_settings.retry_max_seconds,
            retry_jitter_seconds=resolved_settings.retry_jitter_seconds,
            session=session,
            logger=logger,
        )
        return cls(
            http_client=http_client,
            max_reviews_fetch_cap=resolved_settings.reviews_fetch_all_cap,
            maps_no_cache=(
                resolved_settings.serpapi_use_no_cache
                or resolved_settings.serpapi_no_cache
            ),
        )

    def _search_maps(
        self,
        params: SerpApiMapsParams | Mapping[str, Any],
    ) -> SerpApiMapsResponse:
        """Call the SerpAPI google_maps endpoint and return a validated response model."""
        parsed_params = self._parse_params(params=params, params_model=SerpApiMapsParams)
        return self._execute_search(
            parsed_params=parsed_params,
            response_model=SerpApiMapsResponse,
        )

    def _search_maps_reviews(
        self,
        params: SerpApiMapsReviewsParams | Mapping[str, Any],
    ) -> SerpApiMapsReviewsResponse:
        """Call the SerpAPI google_maps_reviews endpoint and return a validated response model."""
        parsed_params = self._parse_params(params=params, params_model=SerpApiMapsReviewsParams)
        return self._execute_search(
            parsed_params=parsed_params,
            response_model=SerpApiMapsReviewsResponse,
        )

    def discover_company_places(self, *, query: str) -> list[DiscoveredPlace]:
        """Run provider search for a query and return all mapped places."""
        scraped_at = datetime.now(tz=UTC)
        maps_response = self._search_maps(SerpApiMapsParams(q=query, no_cache=self._maps_no_cache))
        return map_maps_response_to_discovered_places(
            response=maps_response,
            company_website_url=query,
            provider_name=self.provider_name,
            scraped_at=scraped_at,
        )

    def retrieve_num_reviews(
        self,
        *,
        place: DiscoveredPlace,
        sort_order: ReviewSortOrder | None = None,
        num: int | None = None,
    ) -> list[ReviewRecord]:
        requested_num = _resolve_requested_num(
            num=num,
            max_reviews_fetch_cap=self._max_reviews_fetch_cap,
        )
        scraped_at = datetime.now(tz=UTC)
        resolved_sort_order = _resolve_sort_order_for_records(sort_order)
        serpapi_sort_order = None if sort_order is None else map_sort_order_to_serpapi_value(sort_order)
        cache_key = _build_place_cache_key(place)
        self._histogram_cache.pop(cache_key, None)

        page_token: str | None = None
        collected_reviews: list[ReviewRecord] = []
        review_lookup_identifiers = _build_reviews_lookup_identifiers(place)

        while True:
            reviews_response = self._search_maps_reviews(
                SerpApiMapsReviewsParams(
                    **review_lookup_identifiers,
                    sort_by=serpapi_sort_order,
                    num=_resolve_page_size_for_request(page_token=page_token),
                    next_page_token=page_token,
                )
            )
            if cache_key not in self._histogram_cache:
                cached_histogram = map_reviews_response_to_review_histogram(
                    response=reviews_response,
                    place=place,
                    scraped_at=scraped_at,
                )
                if cached_histogram is not None:
                    self._histogram_cache[cache_key] = cached_histogram
                else:
                    _logger.debug(
                        "serpapi_histogram_not_available place_id=%s data_id=%s "
                        "(SerpAPI reviews endpoint does not return histogram data)",
                        place.place_id,
                        place.data_id,
                    )

            page_reviews = map_reviews_response_to_review_records(
                response=reviews_response,
                place=place,
                sort_order=resolved_sort_order,
                scraped_at=scraped_at,
                rank_offset=len(collected_reviews),
            )
            if not page_reviews:
                break

            collected_reviews.extend(page_reviews)
            if len(collected_reviews) >= requested_num:
                return collected_reviews[:requested_num]

            page_token = reviews_response.pagination.next_page_token if reviews_response.pagination else None
            if not page_token:
                break

        return collected_reviews[:requested_num]

    def retrieve_review_histogram(self, *, place: DiscoveredPlace) -> ReviewHistogram | None:
        """Return cached histogram if available; otherwise return None.

        SerpAPI's reviews endpoint does not return place_result/place_info,
        so histogram data is never present in the response.  Making an API
        call here when the cache is empty would be a wasted request.
        """
        cached_histogram = self._histogram_cache.get(_build_place_cache_key(place))
        if cached_histogram is not None:
            return cached_histogram

        _logger.debug(
            "serpapi_histogram_skip place_id=%s data_id=%s "
            "(no cached histogram and SerpAPI does not provide histogram data)",
            place.place_id,
            place.data_id,
        )
        return None

    def _execute_search(
        self,
        *,
        parsed_params: SerpApiParamsModel,
        response_model: type[ResponseModelT],
    ) -> ResponseModelT:
        """Serialise params, call the HTTP client, and validate the response into the given model."""
        response_payload = self._http_client.perform_request_with_retry(
            params=parsed_params.to_query_params(),
            method="GET",
        )
        return response_model.model_validate(response_payload)

    @staticmethod
    def _parse_params(
        *,
        params: ParamsModelT | Mapping[str, Any],
        params_model: type[ParamsModelT],
    ) -> ParamsModelT:
        """Return params unchanged if already the correct model type; otherwise validate from a mapping."""
        if isinstance(params, params_model):
            return params

        return params_model.model_validate(params)


def _resolve_requested_num(*, num: int | None, max_reviews_fetch_cap: int) -> int:
    """Convert None/-1/positive num to a concrete page count, capped by max_reviews_fetch_cap."""
    if num is None:
        return REVIEWS_PAGE_SIZE
    if num == -1:
        return max_reviews_fetch_cap
    if num >= 1:
        return num
    raise ValueError("`num` must be None, -1, or >= 1.")


def _resolve_page_size_for_request(*, page_token: str | None) -> int | None:
    """Return None for first page (let SerpAPI default); explicit 20 for token-based continuation pages."""
    # SerpAPI may ignore/limit `num` on initial page; explicit 20 is used for token-based pages.
    if page_token is None:
        return None
    return REVIEWS_PAGE_SIZE


def _resolve_sort_order_for_records(sort_order: ReviewSortOrder | None) -> ReviewSortOrder:
    """Map None sort_order to ReviewSortOrder.unspecified for use in review records."""
    if sort_order is None:
        return ReviewSortOrder.unspecified
    return sort_order


def _build_reviews_lookup_identifiers(place: DiscoveredPlace) -> dict[str, str]:
    """
    Build SerpAPI review lookup identifiers.

    SerpAPI rejects requests when both `data_id` and `place_id` are provided together.
    Prefer `data_id` when available; otherwise fallback to `place_id`.
    """
    if place.data_id:
        return {"data_id": place.data_id}
    return {"place_id": place.place_id}


def _build_place_cache_key(place: DiscoveredPlace) -> tuple[str, str]:
    """Return a (provider, place_id) tuple used as a histogram in-memory cache key."""
    return (place.provider, place.place_id)
