"""Opt-in live integration test for SearchAPI with raw payload capture."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from google_reviews.models.searchapi_models import (
    SearchApiMapsParams,
    SearchApiMapsReviewsParams,
)
from google_reviews.providers.retrying_http_client import RetryingHttpClient
from google_reviews.providers.searchapi_client import SearchApiClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_SEARCHAPI_BASE_URL = "https://www.searchapi.io/api/v1/search"
DEFAULT_DATA_ID = "0x8869a03934f4c3a1:0xa088cce21deb1d57"
DEFAULT_MAPS_QUERY = "aptivahealth.com"
ReviewSort = Literal["most_relevant", "newest", "highest_rating", "lowest_rating"]
DEFAULT_REVIEW_SORT: ReviewSort = "newest"


def _is_truthy_env(value: str | None) -> bool:
    if not value:
        return False

    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_searchapi_client(api_key: str, base_url: str) -> SearchApiClient:
    transport = RetryingHttpClient(
        auth_value=api_key,
        auth_query_param_name="api_key",
        service_name="searchapi",
        base_url=base_url,
        timeout_seconds=30,
        retry_attempts=5,
        retry_min_seconds=1,
        retry_max_seconds=20,
        retry_jitter_seconds=0.5,
    )
    return SearchApiClient(http_client=transport)


def _capture_payload(payload: dict[str, Any], filename_prefix: str) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "searchapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"{filename_prefix}_{timestamp}.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_path


def _require_paid_live_settings() -> tuple[str, str]:
    if not _is_truthy_env(os.getenv(RUN_PAID_API_TESTS_ENV_VAR)):
        pytest.skip(f"Set {RUN_PAID_API_TESTS_ENV_VAR}=1 to run paid live API tests.")

    api_key = os.getenv("SEARCHAPI_API_KEY")
    if not api_key:
        pytest.skip("Set SEARCHAPI_API_KEY to run SearchAPI live test.")

    base_url = os.getenv("SEARCHAPI_BASE_URL", DEFAULT_SEARCHAPI_BASE_URL)
    return api_key, base_url


def _resolve_review_sort(value: str | None) -> ReviewSort:
    if value == "most_relevant":
        return "most_relevant"
    if value == "newest":
        return "newest"
    if value == "highest_rating":
        return "highest_rating"
    if value == "lowest_rating":
        return "lowest_rating"

    return DEFAULT_REVIEW_SORT


@pytest.mark.integration
@pytest.mark.paid_api
def test_searchapi_maps_live_capture() -> None:
    """Run a real SearchAPI maps call and persist the response JSON to `tmp/searchapi_live_responses/`."""

    api_key, base_url = _require_paid_live_settings()
    maps_query = os.getenv("TEST_SEARCHAPI_MAPS_QUERY", DEFAULT_MAPS_QUERY)

    client = _build_searchapi_client(api_key=api_key, base_url=base_url)
    response_model = client._search_maps(SearchApiMapsParams(q=maps_query))
    response_payload = response_model.model_dump(mode="json", exclude_none=False)
    output_path = _capture_payload(response_payload, filename_prefix="maps")

    assert response_payload.get("search_metadata")
    assert output_path.exists()


@pytest.mark.integration
@pytest.mark.paid_api
def test_searchapi_maps_reviews_live_capture() -> None:
    """Run a real SearchAPI maps reviews call and persist the response JSON to `tmp/searchapi_live_responses/`."""

    api_key, base_url = _require_paid_live_settings()
    data_id = os.getenv("TEST_SEARCHAPI_DATA_ID", DEFAULT_DATA_ID)
    review_sort = _resolve_review_sort(os.getenv("TEST_SEARCHAPI_REVIEW_SORT", DEFAULT_REVIEW_SORT))

    client = _build_searchapi_client(api_key=api_key, base_url=base_url)
    response_model = client._search_maps_reviews(
        SearchApiMapsReviewsParams(
            data_id=data_id,
            sort_by=review_sort,
            num=20,
        )
    )
    response_payload = response_model.model_dump(mode="json", exclude_none=False)
    output_path = _capture_payload(response_payload, filename_prefix="maps_reviews")

    assert response_payload.get("search_metadata")
    assert output_path.exists()
