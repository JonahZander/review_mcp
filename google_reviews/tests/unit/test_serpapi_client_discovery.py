"""Unit tests for SerpApiClient query-based place discovery."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from google_reviews.models.serpapi_models import SerpApiMapsParams, SerpApiMapsResponse
from google_reviews.providers.retrying_http_client import RetryingHttpClient
from google_reviews.providers.serpapi_client import SerpApiClient


class DiscoverySerpApiClient(SerpApiClient):
    """SerpApiClient test double that returns a predefined maps response."""

    def __init__(self, response: SerpApiMapsResponse, *, maps_no_cache: bool = False) -> None:
        super().__init__(
            http_client=cast(RetryingHttpClient, object()),
            maps_no_cache=maps_no_cache,
        )
        self._response = response
        self.calls: list[SerpApiMapsParams] = []

    def _search_maps(
        self,
        params: SerpApiMapsParams | Mapping[str, Any],
    ) -> SerpApiMapsResponse:
        parsed = params if isinstance(params, SerpApiMapsParams) else SerpApiMapsParams.model_validate(params)
        self.calls.append(parsed)
        return self._response


def _build_maps_response(local_results: list[dict[str, object]]) -> SerpApiMapsResponse:
    return SerpApiMapsResponse.model_validate({"local_results": local_results})


def test_discover_company_places_returns_all_mapped_results_for_query() -> None:
    client = DiscoverySerpApiClient(
        _build_maps_response(
            [
                {"place_id": "p1", "data_id": "d1", "title": "A", "domain": "legacybrainspine.com"},
                {
                    "place_id": "p2",
                    "data_id": "d2",
                    "title": "B",
                    "links": {"website": "https://www.legacybrainspine.com"},
                },
                {"place_id": "p3", "data_id": "d3", "title": "C", "domain": "careers.legacybrainspine.com"},
                {"place_id": "p4", "data_id": "d4", "title": "D", "domain": "other-company.com"},
            ]
        )
    )

    places = client.discover_company_places(query="https://legacybrainspine.com/path")

    assert [place.place_id for place in places] == ["p1", "p2", "p3", "p4"]
    assert len(client.calls) == 1
    assert client.calls[0].q == "https://legacybrainspine.com/path"


def test_discover_company_places_allows_arbitrary_query_string() -> None:
    client = DiscoverySerpApiClient(
        _build_maps_response(
            [
                {"place_id": "p1", "data_id": "d1", "title": "A", "domain": "legacybrainspine.com"},
            ]
        )
    )

    places = client.discover_company_places(query="legacy brain and spine marietta")

    assert len(places) == 1
    assert client.calls[0].q == "legacy brain and spine marietta"


def test_discover_company_places_can_set_no_cache_parameter() -> None:
    client = DiscoverySerpApiClient(
        _build_maps_response(
            [
                {"place_id": "p1", "data_id": "d1", "title": "A", "domain": "legacybrainspine.com"},
            ]
        ),
        maps_no_cache=True,
    )

    places = client.discover_company_places(query="legacybrainspine.com")

    assert len(places) == 1
    assert client.calls[0].no_cache is True
