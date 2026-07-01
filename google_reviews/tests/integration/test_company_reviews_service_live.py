"""Opt-in live integration test for CompanyReviewService.get_company_overview (legacy)."""

from __future__ import annotations

import os

import psycopg
import pytest
from google_reviews.config import Settings
from google_reviews.providers.bootstrap import create_maps_provider_from_settings
from google_reviews.services.company_review_service import CompanyReviewService
from google_reviews.storage.bootstrap import create_postgres_repository_from_settings
from pydantic import ValidationError

RUN_PAID_API_TESTS_ENV_VAR = "RUN_PAID_API_TESTS"
TARGET_COMPANY_URL = os.getenv("TEST_COMPANY_URL", "legacybrainspine.com")


def _is_truthy_env(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_live_settings() -> Settings:
    if not _is_truthy_env(os.getenv(RUN_PAID_API_TESTS_ENV_VAR)):
        pytest.skip(f"Set {RUN_PAID_API_TESTS_ENV_VAR}=1 to run paid live API tests.")

    try:
        return Settings(search_provider="serpapi")
    except ValidationError as exc:
        pytest.skip(
            "Missing required config for live service test. Ensure SERPAPI_API_KEY and POSTGRES_DSN "
            f"are set in environment or .env. Details: {exc.errors()}"
        )


@pytest.mark.integration
@pytest.mark.paid_api
def test_service_live_company_overview_and_persists() -> None:
    """Run live get_company_overview and verify a non-empty result is returned."""

    settings = _require_live_settings()
    provider = create_maps_provider_from_settings(settings=settings)
    assert provider.provider_name == "serpapi"

    try:
        repository, pool = create_postgres_repository_from_settings(
            settings=settings,
            pool_min_size=1,
            pool_max_size=2,
            initialize_schema=True,
        )
    except psycopg.OperationalError as exc:
        pytest.skip(f"Could not connect to PostgreSQL: {exc}")
        return

    service = CompanyReviewService(provider=provider, repository=repository)

    try:
        result = service.get_company_overview(
            company_url=TARGET_COMPANY_URL,
            max_companies=2,
            max_reviews_per_sort=5,
        )

        assert result
        assert result != "No places found."

    finally:
        pool.close()
