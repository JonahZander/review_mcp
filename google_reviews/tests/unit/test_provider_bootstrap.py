"""Unit tests for provider bootstrap helpers."""

from __future__ import annotations

from google_reviews.config import Settings
from google_reviews.providers import bootstrap
from pytest import MonkeyPatch


def test_create_maps_provider_from_settings_searchapi(monkeypatch: MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_searchapi_from_settings(*, settings: Settings, session: object, logger: object) -> str:
        calls["provider"] = "searchapi"
        calls["settings"] = settings
        calls["session"] = session
        calls["logger"] = logger
        return "searchapi-client"

    monkeypatch.setattr(bootstrap.SearchApiClient, "from_settings", fake_searchapi_from_settings)

    settings = Settings(
        search_provider="searchapi",
        searchapi_api_key="searchapi-key",
        postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
    )
    provider = bootstrap.create_maps_provider_from_settings(settings=settings, session=None, logger=None)

    assert provider == "searchapi-client"
    assert calls["provider"] == "searchapi"


def test_create_maps_provider_from_settings_serpapi(monkeypatch: MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_serpapi_from_settings(*, settings: Settings, session: object, logger: object) -> str:
        calls["provider"] = "serpapi"
        calls["settings"] = settings
        calls["session"] = session
        calls["logger"] = logger
        return "serpapi-client"

    monkeypatch.setattr(bootstrap.SerpApiClient, "from_settings", fake_serpapi_from_settings)

    settings = Settings(
        search_provider="serpapi",
        serpapi_api_key="serpapi-key",
        postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
    )
    provider = bootstrap.create_maps_provider_from_settings(settings=settings, session=None, logger=None)

    assert provider == "serpapi-client"
    assert calls["provider"] == "serpapi"
