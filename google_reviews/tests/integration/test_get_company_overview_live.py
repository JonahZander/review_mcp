"""Opt-in live integration test for CompanyReviewService.get_company_overview."""

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
DEFAULT_MAX_COMPANIES = 2
DEFAULT_MAX_REVIEWS_PER_SORT = 5


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


def _summarize_data_sources(log_messages: list[str]) -> dict[str, int]:
    """Count cache hits vs fresh API queries from captured log messages."""
    summary: dict[str, int] = {
        "places_cache_hit": 0,
        "places_api_query": 0,
        "reviews_cache_hit": 0,
        "reviews_api_query": 0,
    }
    for msg in log_messages:
        if "search_company_places cache_hit" in msg or "ensure_places" in msg and "cache" in msg:
            summary["places_cache_hit"] += 1
        if "discover_places trying" in msg:
            summary["places_api_query"] += 1
        if "reviews cache_hit" in msg:
            summary["reviews_cache_hit"] += 1
        if "retrieve_num_reviews" in msg or ("get_place_reviews started" in msg and "reviews cache_hit" not in msg):
            summary["reviews_api_query"] += 1
    return summary


def _write_markdown_log(
    *,
    function_name: str,
    company_url: str,
    max_companies: int,
    max_reviews_per_sort: int,
    data_sources: dict[str, int],
    result: str,
    log_messages: list[str],
    duration_ms: float,
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "service_live_tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"get_company_overview_{timestamp_slug}.md"

    markdown = "\n".join([
        f"# {function_name} - Live Test Log",
        "",
        "## Test Parameters",
        f"- **company_url**: `{company_url}`",
        f"- **max_companies**: {max_companies}",
        f"- **max_reviews_per_sort**: {max_reviews_per_sort}",
        "- **sort_orders**: best, worst, newest, most_relevant",
        f"- **timestamp_utc**: {timestamp.isoformat()}",
        f"- **duration_ms**: {duration_ms:.1f}",
        "",
        "## Data Source Summary",
        f"- **places_cache_hit**: {data_sources['places_cache_hit']}",
        f"- **places_api_query**: {data_sources['places_api_query']}",
        f"- **reviews_cache_hit**: {data_sources['reviews_cache_hit']}",
        f"- **reviews_api_query**: {data_sources['reviews_api_query']}",
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
def test_get_company_overview_live() -> None:
    """Run get_company_overview against a real provider + DB and log the full result."""
    settings = _require_live_settings()
    company_url = os.getenv("TEST_COMPANY_URL", DEFAULT_COMPANY_URL)
    max_companies = int(os.getenv("TEST_MAX_COMPANIES", str(DEFAULT_MAX_COMPANIES)))
    max_reviews_per_sort = int(os.getenv("TEST_MAX_REVIEWS_PER_SORT", str(DEFAULT_MAX_REVIEWS_PER_SORT)))

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
        result = service.get_company_overview(
            company_url=company_url,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
        )
        duration_ms = (datetime.now(tz=UTC) - start).total_seconds() * 1000

        data_sources = _summarize_data_sources(capture.messages())
        output_path = _write_markdown_log(
            function_name="get_company_overview",
            company_url=company_url,
            max_companies=max_companies,
            max_reviews_per_sort=max_reviews_per_sort,
            data_sources=data_sources,
            result=result,
            log_messages=capture.messages(),
            duration_ms=duration_ms,
        )

        assert output_path.exists()
        assert result
        assert result != "No places found."
        print(f"\n--- get_company_overview result written to {output_path} ---")
        print(f"--- data sources: {data_sources} ---")
        print(f"--- duration: {duration_ms:.1f}ms ---")
        print(f"--- output length: {len(result)} chars ---")

    finally:
        service_logger.removeHandler(capture)
        pool.close()
