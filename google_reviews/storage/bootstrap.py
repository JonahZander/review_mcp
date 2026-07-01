"""Helpers for constructing and initializing PostgreSQL-backed repositories."""

from __future__ import annotations

from ..config import Settings, get_settings
from .postgres import PsycopgConnectionPool
from .review_repository import PostgresReviewsRepository


def create_postgres_repository(
    *,
    dsn: str,
    pool_min_size: int = 1,
    pool_max_size: int = 5,
    initialize_schema: bool = True,
) -> tuple[PostgresReviewsRepository, PsycopgConnectionPool]:
    """Create repository + pool and optionally initialize schema."""

    pool = PsycopgConnectionPool(dsn=dsn, min_size=pool_min_size, max_size=pool_max_size)
    repository = PostgresReviewsRepository(pool=pool)
    if initialize_schema:
        repository.initialize_schema()
    return repository, pool


def create_postgres_repository_from_settings(
    *,
    settings: Settings | None = None,
    pool_min_size: int = 1,
    pool_max_size: int = 5,
    initialize_schema: bool = True,
) -> tuple[PostgresReviewsRepository, PsycopgConnectionPool]:
    """Create repository + pool from environment-backed settings."""

    resolved_settings = settings or get_settings()
    return create_postgres_repository(
        dsn=resolved_settings.postgres_dsn,
        pool_min_size=pool_min_size,
        pool_max_size=pool_max_size,
        initialize_schema=initialize_schema,
    )
