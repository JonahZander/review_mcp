"""Unit tests for PostgreSQL repository bootstrap helpers."""

from __future__ import annotations

from google_reviews.config import Settings
from google_reviews.storage import bootstrap
from pytest import MonkeyPatch


def test_create_postgres_repository_initializes_schema_when_enabled(monkeypatch: MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    class FakePool:
        def __init__(self, *, dsn: str, min_size: int, max_size: int) -> None:
            calls["pool"] = (dsn, min_size, max_size)

    class FakeRepository:
        def __init__(self, *, pool: FakePool) -> None:
            calls["repository_pool"] = pool
            calls["schema_initialized"] = False

        def initialize_schema(self) -> None:
            calls["schema_initialized"] = True

    monkeypatch.setattr(bootstrap, "PsycopgConnectionPool", FakePool)
    monkeypatch.setattr(bootstrap, "PostgresReviewsRepository", FakeRepository)

    repository, _pool = bootstrap.create_postgres_repository(
        dsn="postgresql://user:pass@localhost:5432/google_reviews",
        pool_min_size=2,
        pool_max_size=8,
        initialize_schema=True,
    )

    assert calls["pool"] == ("postgresql://user:pass@localhost:5432/google_reviews", 2, 8)
    assert calls["repository_pool"] is not None
    assert calls["schema_initialized"] is True
    assert repository is not None


def test_create_postgres_repository_from_settings_uses_postgres_dsn(monkeypatch: MonkeyPatch) -> None:
    calls: dict[str, object] = {}

    def fake_create_postgres_repository(
        *,
        dsn: str,
        pool_min_size: int,
        pool_max_size: int,
        initialize_schema: bool,
    ) -> tuple[str, str]:
        calls["args"] = (dsn, pool_min_size, pool_max_size, initialize_schema)
        return "repo", "pool"

    monkeypatch.setattr(bootstrap, "create_postgres_repository", fake_create_postgres_repository)

    settings = Settings(
        searchapi_api_key="x",
        postgres_dsn="postgresql://postgres:postgres@localhost:5432/google_reviews",
    )
    repository, pool = bootstrap.create_postgres_repository_from_settings(
        settings=settings,
        pool_min_size=3,
        pool_max_size=6,
        initialize_schema=False,
    )

    assert calls["args"] == ("postgresql://postgres:postgres@localhost:5432/google_reviews", 3, 6, False)
    assert repository == "repo"
    assert pool == "pool"
