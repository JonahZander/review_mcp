"""Unit tests for SearchApiClient review pagination behavior."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from google_reviews.models.domain_models import DiscoveredPlace, ReviewSortOrder
from google_reviews.models.searchapi_models import SearchApiMapsReviewsParams, SearchApiMapsReviewsResponse
from google_reviews.providers.retrying_http_client import RetryingHttpClient
from google_reviews.providers.searchapi_client import SearchApiClient


class PagingSearchApiClient(SearchApiClient):
    """SearchApiClient test double that returns predefined review pages."""

    def __init__(self, responses: list[SearchApiMapsReviewsResponse], *, max_reviews_fetch_cap: int = 100) -> None:
        super().__init__(
            http_client=cast(RetryingHttpClient, object()),
            max_reviews_fetch_cap=max_reviews_fetch_cap,
        )
        self._responses = responses
        self.calls: list[SearchApiMapsReviewsParams] = []

    def _search_maps_reviews(
        self,
        params: SearchApiMapsReviewsParams | Mapping[str, Any],
    ) -> SearchApiMapsReviewsResponse:
        parsed = (
            params
            if isinstance(params, SearchApiMapsReviewsParams)
            else SearchApiMapsReviewsParams.model_validate(params)
        )
        self.calls.append(parsed)
        if not self._responses:
            raise AssertionError("No queued responses left for test.")
        return self._responses.pop(0)


def _build_reviews_response(
    *,
    start_id: int,
    count: int,
    next_page_token: str | None = None,
    include_histogram: bool = False,
) -> SearchApiMapsReviewsResponse:
    reviews = [
        {
            "review_id": f"r-{index}",
            "rating": 5,
            "text": f"review-{index}",
            "iso_date": "2026-01-01T00:00:00Z",
        }
        for index in range(start_id, start_id + count)
    ]

    payload: dict[str, object] = {"reviews": reviews}
    if include_histogram:
        payload["place_result"] = {
            "title": "Aptiva Health",
            "reviews": count,
            "reviews_histogram": {"1": 1, "2": 2, "3": 3, "4": 4, "5": 5},
        }
    if next_page_token:
        payload["pagination"] = {"next_page_token": next_page_token}
    return SearchApiMapsReviewsResponse.model_validate(payload)


def _build_place() -> DiscoveredPlace:
    return DiscoveredPlace.model_validate(
        {
            "provider": "searchapi",
            "place_id": "pid-1",
            "data_id": "did-1",
            "company_website_url": "https://aptivahealth.com",
            "name": "Aptiva Health",
            "website_domain": "aptivahealth.com",
            "scraped_at": "2026-01-01T00:00:00Z",
        }
    )


def test_retrieve_num_reviews_defaults_to_first_20() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=20, next_page_token="token-2"),
        ]
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        sort_order=ReviewSortOrder.newest,
    )

    assert len(reviews) == 20
    assert len(client.calls) == 1
    assert client.calls[0].num == 20
    assert client.calls[0].next_page_token is None


def test_retrieve_num_reviews_omits_sort_by_when_sort_order_not_provided() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=20),
        ]
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        num=20,
    )

    assert len(reviews) == 20
    assert client.calls[0].sort_by is None
    assert all(review.sort_order == ReviewSortOrder.unspecified for review in reviews)


def test_retrieve_num_reviews_paginates_until_requested_count() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=20, next_page_token="token-2"),
            _build_reviews_response(start_id=21, count=20),
        ]
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        sort_order=ReviewSortOrder.best,
        num=35,
    )

    assert len(reviews) == 35
    assert [review.sort_rank for review in reviews] == list(range(1, 36))
    assert len(client.calls) == 2
    assert client.calls[0].num == 20
    assert client.calls[1].num == 20
    assert client.calls[1].next_page_token == "token-2"


def test_retrieve_num_reviews_with_minus_one_fetches_all_pages() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=20, next_page_token="token-2"),
            _build_reviews_response(start_id=21, count=7),
        ]
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        sort_order=ReviewSortOrder.worst,
        num=-1,
    )

    assert len(reviews) == 27
    assert [review.sort_rank for review in reviews] == list(range(1, 28))
    assert len(client.calls) == 2


def test_retrieve_num_reviews_with_minus_one_respects_configured_cap() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=20, next_page_token="token-2"),
            _build_reviews_response(start_id=21, count=20, next_page_token="token-3"),
            _build_reviews_response(start_id=41, count=20),
        ],
        max_reviews_fetch_cap=25,
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        sort_order=ReviewSortOrder.worst,
        num=-1,
    )

    assert len(reviews) == 25
    assert [review.sort_rank for review in reviews] == list(range(1, 26))
    assert len(client.calls) == 2


def test_retrieve_num_reviews_rejects_zero() -> None:
    client = PagingSearchApiClient(responses=[])
    with pytest.raises(ValueError, match="num"):
        client.retrieve_num_reviews(
            place=_build_place(),
            sort_order=ReviewSortOrder.newest,
            num=0,
        )


def test_retrieve_review_histogram_uses_cached_first_page_histogram() -> None:
    client = PagingSearchApiClient(
        responses=[
            _build_reviews_response(
                start_id=1,
                count=20,
                include_histogram=True,
            ),
        ]
    )

    place = _build_place()
    _ = client.retrieve_num_reviews(
        place=place,
        sort_order=ReviewSortOrder.newest,
        num=20,
    )
    histogram = client.retrieve_review_histogram(place=place)

    assert histogram is not None
    assert histogram.star_5 == 5
    assert len(client.calls) == 1
