"""Opt-in live test that captures discover_company_places wrapper output in markdown."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest
from google_reviews.config import Settings, get_settings
from google_reviews.models.domain_models import DiscoveredPlace
from google_reviews.providers.searchapi_client import SearchApiClient
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_COMPANY_URL = "legacybrainspine.com"


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
            "Missing required config for live SearchAPI discover_company_places test. "
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
    discovered_places_payload: list[dict[str, object]],
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "searchapi_live_responses"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"discover_company_places_capture_{timestamp_slug}.md"

    domain_match_count = sum(
        1 for place in discovered_places_payload if place.get("domain_matches_query_domain")
    )

    markdown = "\n".join(
        [
            "# discover_company_places Wrapper Capture",
            "",
            "## Context",
            f"- captured_at_utc: {timestamp.isoformat()}",
            f"- company_url: `{company_url}`",
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
def test_discover_company_places_wrapper_markdown_capture() -> None:
    """Run the wrapper function directly and persist its output model representation."""

    settings = _require_paid_live_settings()
    company_url = os.getenv("TEST_SEARCHAPI_COMPANY_URL", DEFAULT_COMPANY_URL)
    client = SearchApiClient.from_settings(settings=settings)

    discovered_places = client.discover_company_places(
        query=company_url,
    )
    discovered_places_payload = _to_payload_with_match_flags(
        company_url=company_url,
        discovered_places=discovered_places,
    )
    output_path = _write_markdown_capture(
        company_url=company_url,
        discovered_places_payload=discovered_places_payload,
    )

    assert output_path.exists()
    assert len(discovered_places_payload) > 0
