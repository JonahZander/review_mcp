"""Opt-in live test for SerpAPI retrieve_num_reviews using a fixed company place object."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google_reviews.config import Settings
from google_reviews.models.domain_models import DiscoveredPlace, ReviewSortOrder
from google_reviews.providers.serpapi_client import SerpApiClient
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"

FIXED_PLACE_OBJECT: dict[str, object] = {
    "provider": "serpapi",
    "place_id": "ChIJAQB80UYU9YgRb1iqg8_a7rQ",
    "data_id": "0x88f51446d17c0001:0xb4eedacf83aa586f",
    "company_website_url": "legacybrainspine.com",
    "name": "Legacy Brain & Spine, LLC",
    "address": "718 Cherokee St NE Ste 10, Marietta, GA 30060",
    "website_domain": "legacybrainspine.com",
    "rating": 4.6,
    "reviews_count": 316,
    "scraped_at": "2026-02-13T22:04:14.949353Z",
    "is_deleted": False,
    "raw_payload": {
        "place_id": "ChIJAQB80UYU9YgRb1iqg8_a7rQ",
        "data_id": "0x88f51446d17c0001:0xb4eedacf83aa586f",
        "title": "Legacy Brain & Spine, LLC",
        "address": "718 Cherokee St NE Ste 10, Marietta, GA 30060",
        "rating": 4.6,
        "reviews": 316,
        "website": "https://www.legacybrainspine.com/",
        "domain": "legacybrainspine.com",
    },
}


def _is_truthy_env(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_paid_live_settings_for_serpapi() -> Settings:
    if not _is_truthy_env(os.getenv(RUN_PAID_API_TESTS_ENV_VAR)):
        pytest.skip(f"Set {RUN_PAID_API_TESTS_ENV_VAR}=1 to run paid live API tests.")

    try:
        return Settings(search_provider="serpapi")
    except ValidationError as exc:
        pytest.skip(
            "Missing required config for live SerpAPI retrieve_num_reviews test. Ensure "
            f"SERPAPI_API_KEY and POSTGRES_DSN are set. Details: {exc.errors()}"
        )


def _write_markdown_capture(
    *,
    place: DiscoveredPlace,
    requested_num: int,
    reviews_payload: list[dict[str, object]],
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "serpapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"serpapi_retrieve_num_reviews_capture_{timestamp_slug}.md"

    markdown = "\n".join(
        [
            "# retrieve_num_reviews Capture (SerpAPI)",
            "",
            "## Context",
            f"- captured_at_utc: {timestamp.isoformat()}",
            f"- place_id: `{place.place_id}`",
            f"- data_id: `{place.data_id}`",
            f"- requested_num: {requested_num}",
            f"- returned_count: {len(reviews_payload)}",
            "",
            "## Returned ReviewRecord List",
            "```json",
            json.dumps(reviews_payload, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


@pytest.mark.integration
@pytest.mark.paid_api
def test_serpapi_retrieve_num_reviews_with_fixed_place_object() -> None:
    """Fetch reviews for a fixed place and persist the resulting list in a markdown capture document."""

    settings = _require_paid_live_settings_for_serpapi()
    client = SerpApiClient.from_settings(settings=settings)
    place = DiscoveredPlace.model_validate(FIXED_PLACE_OBJECT)

    requested_num = int(os.getenv("TEST_SERPAPI_REQUESTED_NUM", "30"))
    requested_sort_order: ReviewSortOrder | None = ReviewSortOrder.newest

    reviews = client.retrieve_num_reviews(
        place=place,
        num=requested_num,
        sort_order=requested_sort_order,
    )
    reviews_payload = [review.model_dump(mode="json", exclude_none=False) for review in reviews]
    output_path = _write_markdown_capture(
        place=place,
        requested_num=requested_num,
        reviews_payload=reviews_payload,
    )

    assert output_path.exists()
    expected_sort_order = requested_sort_order or ReviewSortOrder.unspecified
    assert all(review.sort_order == expected_sort_order for review in reviews)
    assert [review.sort_rank for review in reviews] == list(range(1, len(reviews) + 1))
    assert all(review.place_id == place.place_id for review in reviews)
    assert all(review.data_id == place.data_id for review in reviews)
