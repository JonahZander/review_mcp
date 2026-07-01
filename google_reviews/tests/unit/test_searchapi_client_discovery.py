"""Unit tests for SearchApiClient query-based place discovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from google_reviews.models.searchapi_models import SearchApiMapsParams, SearchApiMapsResponse
from google_reviews.providers.retrying_http_client import RetryingHttpClient
from google_reviews.providers.searchapi_client import SearchApiClient


class DiscoverySearchApiClient(SearchApiClient):
    """SearchApiClient test double that returns a predefined maps response."""

    def __init__(self, response: SearchApiMapsResponse) -> None:
        super().__init__(http_client=cast(RetryingHttpClient, object()))
        self._response = response
        self.calls: list[SearchApiMapsParams] = []

    def _search_maps(
        self,
        params: SearchApiMapsParams | Mapping[str, Any],
    ) -> SearchApiMapsResponse:
        parsed = params if isinstance(params, SearchApiMapsParams) else SearchApiMapsParams.model_validate(params)
        self.calls.append(parsed)
        return self._response


def _build_maps_response(local_results: list[dict[str, object]]) -> SearchApiMapsResponse:
    return SearchApiMapsResponse.model_validate({"local_results": local_results})


def test_discover_company_places_returns_all_mapped_results_for_query() -> None:
    client = DiscoverySearchApiClient(
        _build_maps_response(
            [
                {"place_id": "p1", "data_id": "d1", "title": "A", "domain": "aptivahealth.com"},
                {"place_id": "p2", "data_id": "d2", "title": "B", "domain": "www.aptivahealth.com"},
                {"place_id": "p3", "data_id": "d3", "title": "C", "domain": "careers.aptivahealth.com"},
                {"place_id": "p4", "data_id": "d4", "title": "D", "domain": "other-company.com"},
            ]
        )
    )

    places = client.discover_company_places(query="https://aptivahealth.com/path")

    assert [place.place_id for place in places] == ["p1", "p2", "p3", "p4"]
    assert len(client.calls) == 1
    assert client.calls[0].q == "https://aptivahealth.com/path"


def test_discover_company_places_allows_arbitrary_query_string() -> None:
    client = DiscoverySearchApiClient(
        _build_maps_response(
            [
                {"place_id": "p1", "data_id": "d1", "title": "A", "domain": "aptivahealth.com"},
            ]
        )
    )

    places = client.discover_company_places(query="aptiva health atlanta")

    assert len(places) == 1
    assert client.calls[0].q == "aptiva health atlanta"
