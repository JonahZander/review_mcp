"""Unit tests for SearchAPI-to-domain mapper behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from google_reviews.models.domain_models import ReviewSortOrder
from google_reviews.models.searchapi_models import SearchApiMapsResponse, SearchApiMapsReviewsResponse
from google_reviews.providers.mappers.searchapi_mapper import (
    map_maps_response_to_discovered_places,
    map_reviews_response_to_review_records,
    map_sort_order_to_searchapi_value,
)


def test_map_reviews_response_preserves_provider_order() -> None:
    response = SearchApiMapsReviewsResponse.model_validate(
        {
            "reviews": [
                {
                    "review_id": "r-1",
                    "rating": 5,
                    "text": "first",
                    "iso_date": "2026-01-01T12:00:00Z",
                },
                {
                    "rating": 4,
                    "text": "second-without-id",
                    "iso_date": "2026-01-02T12:00:00Z",
                },
            ]
        }
    )
    place = map_maps_response_to_discovered_places(
        response=SearchApiMapsResponse.model_validate(
            {
                "local_results": [
                    {
                        "place_id": "pid-1",
                        "data_id": "did-1",
                        "title": "Aptiva Health",
                        "domain": "aptivahealth.com",
                    }
                ]
            }
        ),
        company_website_url="https://aptivahealth.com",
        provider_name="searchapi",
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
    response = SearchApiMapsResponse.model_validate(
        {
            "local_results": [
                {"place_id": "pid-1", "data_id": "did-1", "title": "First", "domain": "aptivahealth.com"},
                {"place_id": "pid-1", "data_id": "did-1", "title": "Duplicate", "domain": "aptivahealth.com"},
                {"place_id": "pid-2", "data_id": "did-2", "title": "Second", "domain": "aptivahealth.com"},
            ]
        }
    )

    places = map_maps_response_to_discovered_places(
        response=response,
        company_website_url="https://aptivahealth.com",
        provider_name="searchapi",
        scraped_at=datetime.now(tz=UTC),
    )

    assert [place.place_id for place in places] == ["pid-1", "pid-2"]


def test_sort_mapping_is_contract_stable() -> None:
    assert map_sort_order_to_searchapi_value(ReviewSortOrder.newest) == "newest"
    assert map_sort_order_to_searchapi_value(ReviewSortOrder.best) == "highest_rating"
    assert map_sort_order_to_searchapi_value(ReviewSortOrder.worst) == "lowest_rating"
    assert map_sort_order_to_searchapi_value(ReviewSortOrder.most_relevant) == "most_relevant"
    with pytest.raises(ValueError, match="Unsupported sort_order"):
        _ = map_sort_order_to_searchapi_value(ReviewSortOrder.unspecified)
