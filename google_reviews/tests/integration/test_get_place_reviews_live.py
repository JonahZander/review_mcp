"""Opt-in live integration test for CompanyReviewService.get_place_reviews."""

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
from google_reviews.storage.base_repository import ReviewsRepository
from google_reviews.storage.bootstrap import create_postgres_repository_from_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
DEFAULT_COMPANY_URL = "legacybrainspine.com"
DEFAULT_NUM_REVIEWS = 15
DEFAULT_SORT_ORDER = "best"


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


def _extract_data_id_from_db(repository: ReviewsRepository, company_url: str) -> str | None:
    """Get the first data_id from the current run's overview for a company URL."""
    overview = repository.get_current_company_overview(
        company_website_url=company_url,
        limit_per_sort=1,
        include_most_relevant=False,
    )
    if overview is None or not overview.locations:
        return None
    for loc in overview.locations:
        if loc.data_id:
            return loc.data_id
    return None


def _detect_data_source(log_messages: list[str]) -> str:
    for msg in log_messages:
        if "reviews cache_hit" in msg:
            return "database (cache hit)"
    return "provider API (fresh query)"


def _write_markdown_log(
    *,
    function_name: str,
    data_id: str,
    num_reviews: int,
    sort_order: str,
    data_source: str,
    places_source: str,
    result: str,
    log_messages: list[str],
    duration_ms: float,
) -> Path:
    output_dir = PROJECT_ROOT / "tmp" / "service_live_tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(tz=UTC)
    timestamp_slug = timestamp.strftime("%Y%m%dT%H%M%SZ")
    output_path = output_dir / f"get_place_reviews_{timestamp_slug}.md"

    markdown = "\n".join([
        f"# {function_name} - Live Test Log",
        "",
        "## Test Parameters",
        f"- **data_id**: `{data_id}`",
        f"- **num_reviews**: {num_reviews}",
        f"- **sort_order**: {sort_order}",
        f"- **timestamp_utc**: {timestamp.isoformat()}",
        f"- **duration_ms**: {duration_ms:.1f}",
        "",
        "## Data Source",
        f"- **places prerequisite**: {places_source}",
        f"- **reviews source**: {data_source}",
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
def test_get_place_reviews_live() -> None:
    """Ensure a place exists via search_company_places, then fetch reviews and log the result."""
    settings = _require_live_settings()
    company_url = os.getenv("TEST_COMPANY_URL", DEFAULT_COMPANY_URL)
    num_reviews = int(os.getenv("TEST_NUM_REVIEWS", str(DEFAULT_NUM_REVIEWS)))
    sort_order = os.getenv("TEST_SORT_ORDER", DEFAULT_SORT_ORDER)

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
        from google_reviews.services.company_review_service import normalize_company_url

        explicit_data_id = os.getenv("TEST_DATA_ID")
        if explicit_data_id:
            data_id = explicit_data_id.strip()
            places_source = "skipped (TEST_DATA_ID provided directly)"
        else:
            canonical_url, _ = normalize_company_url(company_url)

            data_id = _extract_data_id_from_db(repository, canonical_url)
            if data_id is not None:
                places_source = "database (already existed)"
            else:
                service.search_company_places(company_url=company_url)
                data_id = _extract_data_id_from_db(repository, canonical_url)
                places_source = "provider API (discovered in this run)"

            assert data_id is not None, f"No place with data_id found for {company_url}"

        capture.records.clear()

        start = datetime.now(tz=UTC)
        result = service.get_place_reviews(
            data_id=data_id,
            num_reviews=num_reviews,
            sort_order=sort_order,
        )
        duration_ms = (datetime.now(tz=UTC) - start).total_seconds() * 1000

        data_source = _detect_data_source(capture.messages())
        output_path = _write_markdown_log(
            function_name="get_place_reviews",
            data_id=data_id,
            num_reviews=num_reviews,
            sort_order=sort_order,
            data_source=data_source,
            places_source=places_source,
            result=result,
            log_messages=capture.messages(),
            duration_ms=duration_ms,
        )

        assert output_path.exists()
        assert result
        print(f"\n--- get_place_reviews result written to {output_path} ---")
        print(f"--- places source: {places_source} ---")
        print(f"--- reviews source: {data_source} ---")
        print(f"--- duration: {duration_ms:.1f}ms ---")

    finally:
        service_logger.removeHandler(capture)
        pool.close()
