"""Unit tests for SerpApiClient review pagination behavior."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

import pytest
from google_reviews.models.domain_models import DiscoveredPlace, ReviewSortOrder
from google_reviews.models.serpapi_models import SerpApiMapsReviewsParams, SerpApiMapsReviewsResponse
from google_reviews.providers.retrying_http_client import RetryingHttpClient
from google_reviews.providers.serpapi_client import SerpApiClient


class PagingSerpApiClient(SerpApiClient):
    """SerpApiClient test double that returns predefined review pages."""

    def __init__(self, responses: list[SerpApiMapsReviewsResponse], *, max_reviews_fetch_cap: int = 100) -> None:
        super().__init__(
            http_client=cast(RetryingHttpClient, object()),
            max_reviews_fetch_cap=max_reviews_fetch_cap,
        )
        self._responses = responses
        self.calls: list[SerpApiMapsReviewsParams] = []

    def _search_maps_reviews(
        self,
        params: SerpApiMapsReviewsParams | Mapping[str, Any],
    ) -> SerpApiMapsReviewsResponse:
        parsed = (
            params
            if isinstance(params, SerpApiMapsReviewsParams)
            else SerpApiMapsReviewsParams.model_validate(params)
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
) -> SerpApiMapsReviewsResponse:
    reviews = [
        {
            "review_id": f"r-{index}",
            "rating": 5,
            "snippet": f"review-{index}",
            "iso_date": "2026-01-01T00:00:00Z",
        }
        for index in range(start_id, start_id + count)
    ]

    payload: dict[str, object] = {"reviews": reviews}
    if next_page_token:
        payload["serpapi_pagination"] = {"next_page_token": next_page_token}
    return SerpApiMapsReviewsResponse.model_validate(payload)


def _build_place() -> DiscoveredPlace:
    return DiscoveredPlace.model_validate(
        {
            "provider": "serpapi",
            "place_id": "pid-1",
            "data_id": "did-1",
            "company_website_url": "https://legacybrainspine.com",
            "name": "Legacy Brain & Spine",
            "website_domain": "legacybrainspine.com",
            "scraped_at": "2026-01-01T00:00:00Z",
        }
    )


def test_retrieve_num_reviews_omits_sort_by_when_sort_order_not_provided() -> None:
    client = PagingSerpApiClient(
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
    assert client.calls[0].data_id == "did-1"
    assert client.calls[0].place_id is None
    assert all(review.sort_order == ReviewSortOrder.unspecified for review in reviews)


def test_retrieve_num_reviews_uses_none_num_on_first_page_then_20_after_token() -> None:
    client = PagingSerpApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=10, next_page_token="token-2"),
            _build_reviews_response(start_id=11, count=20),
        ]
    )

    reviews = client.retrieve_num_reviews(
        place=_build_place(),
        sort_order=ReviewSortOrder.newest,
        num=25,
    )

    assert len(reviews) == 25
    assert [review.sort_rank for review in reviews] == list(range(1, 26))
    assert len(client.calls) == 2
    assert client.calls[0].num is None
    assert client.calls[0].sort_by == "newestFirst"
    assert client.calls[0].data_id == "did-1"
    assert client.calls[0].place_id is None
    assert client.calls[1].data_id == "did-1"
    assert client.calls[1].place_id is None
    assert client.calls[1].num == 20
    assert client.calls[1].next_page_token == "token-2"


def test_retrieve_num_reviews_with_minus_one_respects_configured_cap() -> None:
    client = PagingSerpApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=10, next_page_token="token-2"),
            _build_reviews_response(start_id=11, count=20, next_page_token="token-3"),
            _build_reviews_response(start_id=31, count=20),
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
    assert client.calls[0].sort_by == "ratingLow"
    assert client.calls[0].data_id == "did-1"
    assert client.calls[0].place_id is None


def test_retrieve_num_reviews_rejects_zero() -> None:
    client = PagingSerpApiClient(responses=[])
    with pytest.raises(ValueError, match="num"):
        client.retrieve_num_reviews(
            place=_build_place(),
            num=0,
        )


def test_serpapi_reviews_params_rejects_both_place_id_and_data_id() -> None:
    with pytest.raises(ValueError, match="Exactly one of place_id or data_id"):
        _ = SerpApiMapsReviewsParams(
            place_id="pid-1",
            data_id="did-1",
        )


def test_retrieve_num_reviews_falls_back_to_place_id_when_data_id_missing() -> None:
    client = PagingSerpApiClient(
        responses=[
            _build_reviews_response(start_id=1, count=10),
        ]
    )
    place_without_data_id = DiscoveredPlace.model_validate(
        {
            "provider": "serpapi",
            "place_id": "pid-1",
            "data_id": None,
            "company_website_url": "https://legacybrainspine.com",
            "name": "Legacy Brain & Spine",
            "website_domain": "legacybrainspine.com",
            "scraped_at": "2026-01-01T00:00:00Z",
        }
    )

    reviews = client.retrieve_num_reviews(
        place=place_without_data_id,
        num=10,
    )

    assert len(reviews) == 10
    assert client.calls[0].data_id is None
    assert client.calls[0].place_id == "pid-1"
