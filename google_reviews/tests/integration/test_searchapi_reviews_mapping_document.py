"""Opt-in live test that captures review response and domain mappings in markdown."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google_reviews.config import Settings, get_settings
from google_reviews.models.domain_models import DiscoveredPlace, ReviewSortOrder
from google_reviews.models.searchapi_models import SearchApiMapsReviewsParams
from google_reviews.providers.mappers.searchapi_mapper import map_reviews_response_to_review_records
from google_reviews.providers.searchapi_client import SearchApiClient
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_COMPANY_URL = "aptivahealth.com"
FIXED_PLACE_ID = "ChIJocP0NDmgaYgRVx3rHeLMiKA"
FIXED_DATA_ID = "0x8869a03934f4c3a1:0xa088cce21deb1d57"
FIXED_KGMID = "/g/11b6_cq40q"
RAW_PAGE_SIZE = 20


def _is_truthy_env(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_paid_live_settings() -> Settings:
    if not _is_truthy_env(os.getenv(RUN_PAID_API_TESTS_ENV_VAR)):
        pytest.skip(f"Set {RUN_PAID_API_TESTS_ENV_VAR}=1 to run paid live API tests.")

    try:
        return get_settings()
    except ValidationError as exc:
        pytest.skip(
            "Missing required config for live SearchAPI reviews test. Ensure SEARCHAPI_API_KEY and "
            f"POSTGRES_DSN are set in environment or .env. Details: {exc.errors()}"
        )


def _write_markdown_capture(
    *,
    company_url: str,
    place: DiscoveredPlace,
    raw_query_payload: dict[str, object],
    raw_response_payload: dict[str, object],
    mapped_first_page_payload: list[dict[str, object]],
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "searchapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"reviews_mapping_capture_{timestamp_slug}.md"

    markdown = "\n".join(
        [
            "# SearchAPI Reviews Mapping Capture",
            "",
            "## Context",
            f"- captured_at_utc: {timestamp.isoformat()}",
            f"- company_url: `{company_url}`",
            f"- fixed_kgmid: `{FIXED_KGMID}`",
            f"- selected_place_id: `{place.place_id}`",
            f"- selected_data_id: `{place.data_id}`",
            f"- selected_place_name: `{place.name}`",
            f"- selected_place_reviews_count_hint: `{place.reviews_count}`",
            "",
            "## Raw `search_maps_reviews` Query",
            "```json",
            json.dumps(raw_query_payload, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Raw `search_maps_reviews` Response",
            "```json",
            json.dumps(raw_response_payload, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Mapped First-Page `ReviewRecord` List",
            "```json",
            json.dumps(mapped_first_page_payload, indent=2, ensure_ascii=False),
            "```",
            "",
            "<!--",
            "## `retrieve_num_reviews` Query",
            "Temporarily disabled to focus on raw API call and review mapping.",
            "",
            "## `retrieve_num_reviews` Output",
            "Temporarily disabled to focus on raw API call and review mapping.",
            "-->",
            "",
            "## Counts",
            f"- mapped_first_page_count: {len(mapped_first_page_payload)}",
            "",
        ]
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


@pytest.mark.integration
@pytest.mark.paid_api
def test_searchapi_reviews_response_and_mapping_document() -> None:
    """
    Run live review retrieval and save one markdown document with:
    - raw SearchAPI reviews query/response
    - mapped ReviewRecord list (from raw first page)
    """

    settings = _require_paid_live_settings()
    company_url = os.getenv("TEST_SEARCHAPI_COMPANY_URL", DEFAULT_COMPANY_URL)
    client = SearchApiClient.from_settings(settings=settings)

    raw_query_model = SearchApiMapsReviewsParams(
        place_id=FIXED_PLACE_ID,
        data_id=FIXED_DATA_ID,
        sort_by="newest",
        num=RAW_PAGE_SIZE,
    )
    raw_response_model = client._search_maps_reviews(raw_query_model)
    raw_response_payload = raw_response_model.model_dump(mode="json", exclude_none=False)
    raw_query_payload = raw_query_model.model_dump(mode="json", exclude_none=False)

    place = DiscoveredPlace(
        provider=client.provider_name,
        place_id=FIXED_PLACE_ID,
        data_id=FIXED_DATA_ID,
        company_website_url=company_url,
        scraped_at=datetime.now(tz=UTC),
        name=raw_response_model.place_result.title if raw_response_model.place_result else None,
        address=raw_response_model.place_result.address if raw_response_model.place_result else None,
        reviews_count=raw_response_model.place_result.reviews if raw_response_model.place_result else None,
    )

    mapped_first_page = map_reviews_response_to_review_records(
        response=raw_response_model,
        place=place,
        sort_order=ReviewSortOrder.newest,
        scraped_at=datetime.now(tz=UTC),
    )
    mapped_first_page_payload = [
        review.model_dump(mode="json", exclude_none=False) for review in mapped_first_page
    ]

    # retrieve_num_query_payload: dict[str, object] = {
    #     "function": "retrieve_num_reviews",
    #     "place": place.model_dump(mode="json", exclude_none=False),
    #     "sort_order": ReviewSortOrder.newest.value,
    #     "num": 30,
    # }
    # retrieved_reviews = client.retrieve_num_reviews(
    #     place=place,
    #     sort_order=ReviewSortOrder.newest,
    #     num=30,
    # )
    # retrieved_reviews_payload = [
    #     review.model_dump(mode="json", exclude_none=False) for review in retrieved_reviews
    # ]

    output_path = _write_markdown_capture(
        company_url=company_url,
        place=place,
        raw_query_payload=raw_query_payload,
        raw_response_payload=raw_response_payload,
        mapped_first_page_payload=mapped_first_page_payload,
    )

    assert output_path.exists()
    assert raw_response_payload.get("search_metadata")
