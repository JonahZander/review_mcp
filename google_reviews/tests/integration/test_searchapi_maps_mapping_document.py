"""Opt-in live test that captures search_maps response and mapped discovered places in markdown."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from google_reviews.config import Settings, get_settings
from google_reviews.models.searchapi_models import SearchApiMapsParams
from google_reviews.providers.mappers.searchapi_mapper import map_maps_response_to_discovered_places
from google_reviews.providers.searchapi_client import SearchApiClient
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_MAPS_QUERY = "legacybrainspine.com"


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
            "Missing required config for live SearchAPI maps test. Ensure SEARCHAPI_API_KEY and "
            f"POSTGRES_DSN are set in environment or .env. Details: {exc.errors()}"
        )


def _write_markdown_capture(
    *,
    maps_query: str,
    response_payload: dict[str, object],
    discovered_places_payload: list[dict[str, object]],
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "searchapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"maps_discovered_places_{timestamp_slug}.md"

    extracted_with_place_id = sum(1 for place in discovered_places_payload if place.get("place_id"))
    extracted_with_data_id = sum(1 for place in discovered_places_payload if place.get("data_id"))
    extracted_with_domain = sum(1 for place in discovered_places_payload if place.get("website_domain"))

    markdown = "\n".join(
        [
            "# SearchAPI Maps to DiscoveredPlace Capture",
            "",
            "## Context",
            f"- captured_at_utc: {timestamp.isoformat()}",
            f"- query: `{maps_query}`",
            f"- discovered_places_count: {len(discovered_places_payload)}",
            "",
            "## Domain Extraction Quick Check",
            f"- with_place_id: {extracted_with_place_id}",
            f"- with_data_id: {extracted_with_data_id}",
            f"- with_website_domain: {extracted_with_domain}",
            "",
            "## Raw `search_maps` Response (`SearchApiMapsResponse.model_dump`)",
            "```json",
            json.dumps(response_payload, indent=2, ensure_ascii=False),
            "```",
            "",
            "## Mapped `DiscoveredPlace` List",
            "```json",
            json.dumps(discovered_places_payload, indent=2, ensure_ascii=False),
            "```",
            "",
        ]
    )
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


@pytest.mark.integration
@pytest.mark.paid_api
def test_searchapi_maps_response_and_discovered_places_markdown_capture() -> None:
    """
    Run a real `search_maps` request and save one markdown document with:
    - raw SearchApiMapsResponse model dump
    - mapped DiscoveredPlace list representation
    """

    settings = _require_paid_live_settings()
    maps_query = os.getenv("TEST_SEARCHAPI_MAPS_QUERY", DEFAULT_MAPS_QUERY)

    client = SearchApiClient.from_settings(settings=settings)
    response_model = client._search_maps(SearchApiMapsParams(q=maps_query))
    response_payload = response_model.model_dump(mode="json", exclude_none=False)

    discovered_places = map_maps_response_to_discovered_places(
        response=response_model,
        company_website_url=maps_query,
        provider_name=client.provider_name,
        scraped_at=datetime.now(tz=UTC),
    )
    discovered_places_payload = [
        place.model_dump(mode="json", exclude_none=False) for place in discovered_places
    ]

    output_path = _write_markdown_capture(
        maps_query=maps_query,
        response_payload=response_payload,
        discovered_places_payload=discovered_places_payload,
    )

    assert output_path.exists()
    assert response_payload.get("search_metadata")
    assert isinstance(discovered_places_payload, list)
