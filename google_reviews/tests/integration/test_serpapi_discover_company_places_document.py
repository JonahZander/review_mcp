"""Opt-in live test that captures SerpAPI discover_company_places output in markdown."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
from google_reviews.config import Settings
from google_reviews.models.domain_models import DiscoveredPlace
from google_reviews.providers.bootstrap import create_maps_provider_from_settings
from google_reviews.providers.serpapi_client import SerpApiClient
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_COMPANY_URL = "legacybrainspine.com"

logger = logging.getLogger(__name__)


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
            "Missing required config for live SerpAPI discover_company_places test. "
            f"Details: {exc.errors()}"
        )


def _normalize_domain(value: str) -> str | None:
    candidate = value.strip().lower()
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    if not parsed.hostname:
        return None

    normalized = parsed.hostname.lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _to_payload_with_match_flags(
    *,
    company_url: str,
    discovered_places: list[DiscoveredPlace],
) -> list[dict[str, object]]:
    query_domain = _normalize_domain(company_url)
    payload: list[dict[str, object]] = []
    for place in discovered_places:
        place_payload = place.model_dump(mode="json", exclude_none=False)
        place_domain = place.website_domain
        place_payload["query_domain"] = query_domain
        place_payload["domain_matches_query_domain"] = (
            bool(
                query_domain
                and place_domain
                and (
                    place_domain == query_domain
                    or place_domain.endswith(f".{query_domain}")
                    or query_domain.endswith(f".{place_domain}")
                )
            )
        )
        payload.append(place_payload)
    return payload


def _write_markdown_capture(
    *,
    company_url: str,
    no_cache: bool,
    discovered_places_payload: list[dict[str, object]],
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "serpapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"discover_company_places_capture_{timestamp_slug}.md"

    domain_match_count = sum(
        1 for place in discovered_places_payload if place.get("domain_matches_query_domain")
    )

    markdown = "\n".join(
        [
            "# discover_company_places Wrapper Capture (SerpAPI)",
            "",
            "## Context",
            f"- captured_at_utc: {timestamp.isoformat()}",
            f"- company_url: `{company_url}`",
            f"- no_cache: {str(no_cache).lower()}",
            f"- discovered_places_count: {len(discovered_places_payload)}",
            f"- domain_match_count: {domain_match_count}",
            "",
            "## DiscoveredPlace Output",
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
def test_serpapi_discover_company_places_wrapper_markdown_capture() -> None:
    """Run SerpAPI discover wrapper and persist its output model representation."""

    settings = _require_paid_live_settings_for_serpapi()
    company_url = os.getenv("TEST_SERPAPI_COMPANY_URL", DEFAULT_COMPANY_URL)
    test_no_cache_override = os.getenv("TEST_SERPAPI_NO_CACHE")
    no_cache = (
        settings.serpapi_use_no_cache
        if test_no_cache_override is None
        else _is_truthy_env(test_no_cache_override)
    )
    settings = Settings.model_validate(
        {
            **settings.model_dump(mode="python"),
            "serpapi_use_no_cache": no_cache,
        }
    )

    provider = create_maps_provider_from_settings(settings=settings)
    assert isinstance(provider, SerpApiClient)
    client = provider

    logger.info(
        "Starting SerpAPI discover_company_places test",
        extra={"company_url": company_url, "no_cache": no_cache},
    )
    discovered_places = client.discover_company_places(
        query=company_url,
    )
    logger.info("SerpAPI discover_company_places returned %s places", len(discovered_places))

    discovered_places_payload = _to_payload_with_match_flags(
        company_url=company_url,
        discovered_places=discovered_places,
    )
    output_path = _write_markdown_capture(
        company_url=company_url,
        no_cache=no_cache,
        discovered_places_payload=discovered_places_payload,
    )
    logger.info("SerpAPI discover capture written to %s", output_path)

    assert output_path.exists()
    assert len(discovered_places_payload) > 0
