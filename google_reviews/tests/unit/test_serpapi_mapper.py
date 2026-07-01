"""Unit tests for SerpAPI-to-domain mapper behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google_reviews.models.domain_models import ReviewSortOrder
from google_reviews.models.serpapi_models import SerpApiMapsResponse, SerpApiMapsReviewsResponse
from google_reviews.providers.mappers.serpapi_mapper import (
    map_maps_response_to_discovered_places,
    map_reviews_response_to_review_histogram,
    map_reviews_response_to_review_records,
    map_sort_order_to_serpapi_value,
)


def test_map_reviews_response_preserves_provider_order() -> None:
    response = SerpApiMapsReviewsResponse.model_validate(
        {
            "reviews": [
                {
                    "review_id": "r-1",
                    "rating": 5,
                    "snippet": "first",
                    "iso_date": "2026-01-01T12:00:00Z",
                },
                {
                    "rating": 4,
                    "snippet": "second-without-id",
                    "iso_date": "2026-01-02T12:00:00Z",
                },
            ]
        }
    )
    place = map_maps_response_to_discovered_places(
        response=SerpApiMapsResponse.model_validate(
            {
                "local_results": [
                    {
                        "place_id": "pid-1",
                        "data_id": "did-1",
                        "title": "Legacy Brain & Spine",
                        "links": {"website": "https://legacybrainspine.com"},
                    }
                ]
            }
        ),
        company_website_url="https://legacybrainspine.com",
        provider_name="serpapi",
        scraped_at=datetime.now(tz=UTC),
    )[0]

    records = map_reviews_response_to_review_records(
        response=response,
        place=place,
        sort_order=ReviewSortOrder.best,
        scraped_at=datetime.now(tz=UTC),
    )

    assert len(records) == 2
    assert records[0].review_id == "r-1"
    assert records[0].sort_rank == 1
    assert records[1].sort_rank == 2
    assert records[1].review_id.startswith("synthetic_")


def test_map_maps_response_deduplicates_place_id() -> None:
    response = SerpApiMapsResponse.model_validate(
        {
            "local_results": [
                {"place_id": "pid-1", "data_id": "did-1", "title": "First", "domain": "legacybrainspine.com"},
                {"place_id": "pid-1", "data_id": "did-1", "title": "Duplicate", "domain": "legacybrainspine.com"},
                {"place_id": "pid-2", "data_id": "did-2", "title": "Second", "domain": "legacybrainspine.com"},
            ]
        }
    )

    places = map_maps_response_to_discovered_places(
        response=response,
        company_website_url="https://legacybrainspine.com",
        provider_name="serpapi",
        scraped_at=datetime.now(tz=UTC),
    )

    assert [place.place_id for place in places] == ["pid-1", "pid-2"]


def test_map_reviews_histogram_from_rating_summary() -> None:
    response = SerpApiMapsReviewsResponse.model_validate(
        {
            "place_info": {
                "reviews": 30,
                "rating_summary": [
                    {"stars": 5, "amount": 20},
                    {"stars": 4, "amount": 6},
                    {"stars": 3, "amount": 2},
                    {"stars": 2, "amount": 1},
                    {"stars": 1, "amount": 1},
                ],
            }
        }
    )
    place = map_maps_response_to_discovered_places(
        response=SerpApiMapsResponse.model_validate(
            {"local_results": [{"place_id": "pid-1", "data_id": "did-1", "domain": "legacybrainspine.com"}]}
        ),
        company_website_url="https://legacybrainspine.com",
        provider_name="serpapi",
        scraped_at=datetime.now(tz=UTC),
    )[0]

    histogram = map_reviews_response_to_review_histogram(
        response=response,
        place=place,
        scraped_at=datetime.now(tz=UTC),
    )

    assert histogram is not None
    assert histogram.star_5 == 20
    assert histogram.star_1 == 1
    assert histogram.total_reviews == 30


def test_sort_mapping_is_contract_stable() -> None:
    assert map_sort_order_to_serpapi_value(ReviewSortOrder.newest) == "newestFirst"
    assert map_sort_order_to_serpapi_value(ReviewSortOrder.best) == "ratingHigh"
    assert map_sort_order_to_serpapi_value(ReviewSortOrder.worst) == "ratingLow"
    assert map_sort_order_to_serpapi_value(ReviewSortOrder.most_relevant) == "qualityScore"
    with pytest.raises(ValueError, match="Unsupported sort_order"):
        _ = map_sort_order_to_serpapi_value(ReviewSortOrder.unspecified)
