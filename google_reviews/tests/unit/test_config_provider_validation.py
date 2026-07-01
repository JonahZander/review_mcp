"""Unit tests for provider-specific credential validation in settings."""

from __future__ import annotations

import pytest
from google_reviews.config import Settings


def test_settings_requires_searchapi_key_for_searchapi_provider() -> None:
    with pytest.raises(ValueError, match="searchapi_api_key"):
        _ = Settings(
            search_provider="searchapi",
            searchapi_api_key="",
            postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
        )


def test_settings_requires_serpapi_key_for_serpapi_provider() -> None:
    with pytest.raises(ValueError, match="serpapi_api_key"):
        _ = Settings(
            search_provider="serpapi",
            serpapi_api_key="",
            postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
        )


def test_settings_accepts_serpapi_provider_with_serpapi_key() -> None:
    settings = Settings(
        search_provider="serpapi",
        serpapi_api_key="serpapi-key",
        postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
    )
    assert settings.search_provider == "serpapi"
