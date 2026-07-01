"""Opt-in live integration test for CompanyReviewService.search_company_places."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from google_reviews.config import Settings, get_settings
from google_reviews.providers.bootstrap import create_maps_provider_from_settings
from google_reviews.services.company_review_service import CompanyReviewService
from google_reviews.storage.bootstrap import create_postgres_repository_from_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_COMPANY_URL = "legacybrainspine.com"


class _LogCapture(logging.Handler):
    """Collects log records emitted during a test run."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    def messages(self) -> list[str]:
        return [self.format(r) for r in self.records]


def _is_truthy_env(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_live_settings() -> Settings:
    if not _is_truthy_env(os.getenv(RUN_PAID_API_TESTS_ENV_VAR)):
        pytest.skip(f"Set {RUN_PAID_API_TESTS_ENV_VAR}=1 to run paid live API tests.")

    try:
        return get_settings()
    except Exception as exc:
        pytest.skip(f"Missing required config for live service test: {exc}")


def _detect_data_source(log_messages: list[str]) -> str:
    for msg in log_messages:
        if "cache_hit" in msg and "search_company_places" in msg:
            return "database (cache hit)"
    for msg in log_messages:
        if "discover_places trying" in msg:
            return "provider API (fresh query)"
    return "unknown"


def _write_markdown_log(
    *,
    function_name: str,
    company_url: str,
    data_source: str,
    result: str,
    log_messages: list[str],
    duration_ms: float,
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "service_live_tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"search_company_places_{timestamp_slug}.md"

    markdown = "\n".join([
        f"# {function_name} - Live Test Log",
        "",
        "## Test Parameters",
        f"- **company_url**: `{company_url}`",
        f"- **timestamp_utc**: {timestamp.isoformat()}",
        f"- **duration_ms**: {duration_ms:.1f}",
        "",
        "## Data Source",
        f"- **source**: {data_source}",
        "",
        "## Service Log Messages",
        "```",
        *log_messages,
        "```",
        "",
        "## Function Output (returned to LLM)",
        "```",
        result,
        "```",
        "",
    ])
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


@pytest.mark.integration
@pytest.mark.paid_api
def test_search_company_places_live() -> None:
    """Run search_company_places against a real provider + DB and log the result."""
    settings = _require_live_settings()
    company_url = os.getenv("TEST_COMPANY_URL", DEFAULT_COMPANY_URL)

    provider = create_maps_provider_from_settings(settings=settings)
    try:
        repository, pool = create_postgres_repository_from_settings(
            settings=settings, pool_min_size=1, pool_max_size=2, initialize_schema=True,
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"Could not connect to PostgreSQL: {exc}")
        return

    service = CompanyReviewService(provider=provider, repository=repository)

    capture = _LogCapture()
    capture.setFormatter(logging.Formatter("%(levelname)s %(name)s - %(message)s"))
    service_logger = logging.getLogger("google_reviews.services.company_review_service")
    service_logger.addHandler(capture)

    try:
        start = datetime.now(tz=UTC)
        result = service.search_company_places(company_url=company_url)
        duration_ms = (datetime.now(tz=UTC) - start).total_seconds() * 1000

        data_source = _detect_data_source(capture.messages())
        output_path = _write_markdown_log(
            function_name="search_company_places",
            company_url=company_url,
            data_source=data_source,
            result=result,
            log_messages=capture.messages(),
            duration_ms=duration_ms,
        )

        assert output_path.exists()
        assert result
        assert "No places found." not in result or result == "No places found."
        print(f"\n--- search_company_places result written to {output_path} ---")
        print(f"--- data source: {data_source} ---")
        print(f"--- duration: {duration_ms:.1f}ms ---")

    finally:
        service_logger.removeHandler(capture)
        pool.close()
