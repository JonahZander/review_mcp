"""PostgreSQL implementation of the reviews repository contract."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..logging_config import get_logger
from ..models.domain_models import (
    CompanyRecord,
    CompanyReviewOverview,
    DiscoveredPlace,
    LocationOverview,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
    ScrapeRun,
)
from .base_repository import ReviewsRepository
from .postgres import PsycopgConnectionPool

_active_connection: ContextVar[Connection[Any] | None] = ContextVar("active_connection", default=None)


class PostgresReviewsRepository(ReviewsRepository):
    """Repository implementation that stores current and historical scrape runs."""

    def __init__(self, *, pool: PsycopgConnectionPool) -> None:
        """Store the connection pool and initialise the logger."""
        self._pool = pool
        self._logger = get_logger(__name__)

    def close(self) -> None:
        """Close all pooled connections."""
        self._pool.close()

    def initialize_schema(self) -> None:
        """Create all required tables and indexes if they do not already exist."""
        def _operation(connection: Connection[Any]) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS companies (
                        company_website_url TEXT PRIMARY KEY,
                        normalized_website_domain TEXT NOT NULL,
                        display_name TEXT NULL,
                        scraped_at TIMESTAMPTZ NOT NULL,
                        raw_payload JSONB NULL
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_companies_normalized_website_domain
                    ON companies (normalized_website_domain);
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS scrape_runs (
                        scrape_run_id UUID PRIMARY KEY,
                        company_website_url TEXT NOT NULL REFERENCES companies(company_website_url),
                        scraped_at TIMESTAMPTZ NOT NULL,
                        is_current BOOLEAN NOT NULL DEFAULT FALSE,
                        include_most_relevant BOOLEAN NOT NULL DEFAULT TRUE,
                        requested_limit_per_sort INTEGER NOT NULL DEFAULT 20
                    );
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE scrape_runs
                    ADD COLUMN IF NOT EXISTS requested_limit_per_sort INTEGER NOT NULL DEFAULT 20;
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_scrape_runs_one_current_per_company
                    ON scrape_runs (company_website_url)
                    WHERE is_current = TRUE;
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_scrape_runs_company_scraped_at
                    ON scrape_runs (company_website_url, scraped_at DESC);
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS places (
                        scrape_run_id UUID NOT NULL REFERENCES scrape_runs(scrape_run_id),
                        provider TEXT NOT NULL,
                        place_id TEXT NOT NULL,
                        data_id TEXT NULL,
                        company_website_url TEXT NOT NULL REFERENCES companies(company_website_url),
                        name TEXT NULL,
                        address TEXT NULL,
                        website_domain TEXT NULL,
                        rating DOUBLE PRECISION NULL,
                        reviews_count INTEGER NULL,
                        scraped_at TIMESTAMPTZ NOT NULL,
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                        raw_payload JSONB NOT NULL,
                        PRIMARY KEY (scrape_run_id, provider, place_id)
                    );
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_places_company_website_url
                    ON places (company_website_url);
                    """
                )
                cursor.execute(
                    """
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_places_provider_data_id_per_run
                    ON places (provider, data_id, scrape_run_id)
                    WHERE data_id IS NOT NULL;
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reviews (
                        scrape_run_id UUID NOT NULL REFERENCES scrape_runs(scrape_run_id),
                        provider TEXT NOT NULL,
                        place_id TEXT NOT NULL,
                        data_id TEXT NULL,
                        review_id TEXT NOT NULL,
                        sort_order TEXT NOT NULL,
                        sort_rank INTEGER NOT NULL,
                        author_name TEXT NULL,
                        author_contributor_id TEXT NULL,
                        rating INTEGER NULL,
                        text TEXT NULL,
                        translated_text TEXT NULL,
                        likes INTEGER NULL,
                        written_at TIMESTAMPTZ NULL,
                        source TEXT NULL,
                        review_link TEXT NULL,
                        scraped_at TIMESTAMPTZ NOT NULL,
                        is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
                        raw_payload JSONB NOT NULL,
                        PRIMARY KEY (scrape_run_id, provider, place_id, sort_order, sort_rank),
                        UNIQUE (scrape_run_id, provider, place_id, sort_order, review_id)
                    );
                    """
                )
                cursor.execute(
                    """
                    ALTER TABLE reviews
                    ADD COLUMN IF NOT EXISTS data_id TEXT NULL;
                    """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_reviews_run_place_sort_rank
                    ON reviews (scrape_run_id, provider, place_id, sort_order, sort_rank);
                    """
                )
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS review_histograms (
                        scrape_run_id UUID NOT NULL REFERENCES scrape_runs(scrape_run_id),
                        provider TEXT NOT NULL,
                        place_id TEXT NOT NULL,
                        star_1 INTEGER NOT NULL DEFAULT 0,
                        star_2 INTEGER NOT NULL DEFAULT 0,
                        star_3 INTEGER NOT NULL DEFAULT 0,
                        star_4 INTEGER NOT NULL DEFAULT 0,
                        star_5 INTEGER NOT NULL DEFAULT 0,
                        total_reviews INTEGER NULL,
                        scraped_at TIMESTAMPTZ NOT NULL,
                        raw_payload JSONB NOT NULL,
                        PRIMARY KEY (scrape_run_id, provider, place_id)
                    );
                    """
                )

        self._execute_write(_operation)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Context manager that wraps multiple repository operations in a single commit/rollback unit."""
        existing = _active_connection.get()
        if existing is not None:
            yield
            return

        with self._pool.connection() as connection:
            token = _active_connection.set(connection)
            try:
                yield
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                _active_connection.reset(token)

    def upsert_company(self, company: CompanyRecord) -> None:
        """Insert or update a company record keyed on company_website_url."""
        def _operation(connection: Connection[Any]) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO companies (
                        company_website_url,
                        normalized_website_domain,
                        display_name,
                        scraped_at,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (company_website_url)
                    DO UPDATE SET
                        normalized_website_domain = EXCLUDED.normalized_website_domain,
                        display_name = EXCLUDED.display_name,
                        scraped_at = EXCLUDED.scraped_at,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    (
                        company.company_website_url,
                        company.normalized_website_domain,
                        company.display_name,
                        company.scraped_at,
                        Jsonb(company.raw_payload),
                    ),
                )

        self._execute_write(_operation)

    def start_scrape_run(
        self,
        *,
        company_website_url: str,
        include_most_relevant: bool,
        requested_limit_per_sort: int,
        scraped_at: datetime,
    ) -> ScrapeRun:
        """Insert a new (non-current) scrape run row and return the populated ScrapeRun model."""
        scrape_run_id = str(uuid4())

        def _operation(connection: Connection[Any]) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO scrape_runs (
                        scrape_run_id,
                        company_website_url,
                        scraped_at,
                        is_current,
                        include_most_relevant,
                        requested_limit_per_sort
                    )
                    VALUES (%s, %s, %s, FALSE, %s, %s);
                    """,
                    (
                        scrape_run_id,
                        company_website_url,
                        scraped_at,
                        include_most_relevant,
                        requested_limit_per_sort,
                    ),
                )

        self._execute_write(_operation)
        return ScrapeRun(
            scrape_run_id=scrape_run_id,
            company_website_url=company_website_url,
            scraped_at=scraped_at,
            include_most_relevant=include_most_relevant,
            requested_limit_per_sort=requested_limit_per_sort,
            is_current=False,
        )

    def get_current_scrape_run(self, *, company_website_url: str) -> ScrapeRun | None:
        """Return the single is_current run for a company URL, or None if none exists."""
        def _operation(connection: Connection[Any]) -> ScrapeRun | None:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        scrape_run_id,
                        company_website_url,
                        scraped_at,
                        include_most_relevant,
                        requested_limit_per_sort,
                        is_current
                    FROM scrape_runs
                    WHERE company_website_url = %s
                      AND is_current = TRUE
                    ORDER BY scraped_at DESC
                    LIMIT 1;
                    """,
                    (company_website_url,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                return ScrapeRun(
                    scrape_run_id=str(row["scrape_run_id"]),
                    company_website_url=row["company_website_url"],
                    scraped_at=row["scraped_at"],
                    include_most_relevant=row["include_most_relevant"],
                    requested_limit_per_sort=row["requested_limit_per_sort"],
                    is_current=row["is_current"],
                )

        return self._execute_read(_operation)

    def replace_run_places(self, *, scrape_run_id: str, places: list[DiscoveredPlace]) -> int:
        """Delete then re-insert all place rows for a run atomically."""
        def _operation(connection: Connection[Any]) -> int:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM places WHERE scrape_run_id = %s;", (scrape_run_id,))
                if not places:
                    return 0

                cursor.executemany(
                    """
                    INSERT INTO places (
                        scrape_run_id,
                        provider,
                        place_id,
                        data_id,
                        company_website_url,
                        name,
                        address,
                        website_domain,
                        rating,
                        reviews_count,
                        scraped_at,
                        is_deleted,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    [
                        (
                            scrape_run_id,
                            place.provider,
                            place.place_id,
                            place.data_id,
                            place.company_website_url,
                            place.name,
                            place.address,
                            place.website_domain,
                            place.rating,
                            place.reviews_count,
                            place.scraped_at,
                            place.is_deleted,
                            Jsonb(place.raw_payload),
                        )
                        for place in places
                    ],
                )
                return len(places)

        row_count = self._execute_write(_operation)
        self._logger.info("repository_places_replaced scrape_run_id=%s count=%s", scrape_run_id, row_count)
        return row_count

    def replace_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        """Delete then re-insert all review rows for a run atomically."""
        def _operation(connection: Connection[Any]) -> int:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM reviews WHERE scrape_run_id = %s;", (scrape_run_id,))
                if not reviews:
                    return 0

                cursor.executemany(
                    """
                    INSERT INTO reviews (
                        scrape_run_id,
                        provider,
                        place_id,
                        data_id,
                        review_id,
                        sort_order,
                        sort_rank,
                        author_name,
                        author_contributor_id,
                        rating,
                        text,
                        translated_text,
                        likes,
                        written_at,
                        source,
                        review_link,
                        scraped_at,
                        is_deleted,
                        raw_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    );
                    """,
                    [
                        (
                            scrape_run_id,
                            review.provider,
                            review.place_id,
                            review.data_id,
                            review.review_id,
                            review.sort_order.value,
                            review.sort_rank,
                            review.author_name,
                            review.author_contributor_id,
                            review.rating,
                            review.text,
                            review.translated_text,
                            review.likes,
                            review.written_at,
                            review.source,
                            review.review_link,
                            review.scraped_at,
                            review.is_deleted,
                            Jsonb(review.raw_payload),
                        )
                        for review in reviews
                    ],
                )
                return len(reviews)

        row_count = self._execute_write(_operation)
        self._logger.info("repository_reviews_replaced scrape_run_id=%s count=%s", scrape_run_id, row_count)
        return row_count

    def replace_run_histograms(self, *, scrape_run_id: str, histograms: list[ReviewHistogram]) -> int:
        """Delete then re-insert all histogram rows for a run atomically."""
        def _operation(connection: Connection[Any]) -> int:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM review_histograms WHERE scrape_run_id = %s;", (scrape_run_id,))
                if not histograms:
                    return 0

                cursor.executemany(
                    """
                    INSERT INTO review_histograms (
                        scrape_run_id,
                        provider,
                        place_id,
                        star_1,
                        star_2,
                        star_3,
                        star_4,
                        star_5,
                        total_reviews,
                        scraped_at,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    [
                        (
                            scrape_run_id,
                            histogram.provider,
                            histogram.place_id,
                            histogram.star_1,
                            histogram.star_2,
                            histogram.star_3,
                            histogram.star_4,
                            histogram.star_5,
                            histogram.total_reviews,
                            histogram.scraped_at,
                            Jsonb(histogram.raw_payload),
                        )
                        for histogram in histograms
                    ],
                )
                return len(histograms)

        row_count = self._execute_write(_operation)
        self._logger.info("repository_histograms_replaced scrape_run_id=%s count=%s", scrape_run_id, row_count)
        return row_count

    def set_scrape_run_current(self, *, company_website_url: str, scrape_run_id: str) -> None:
        """Demote any existing current run and promote the given run, then sync company scraped_at."""
        def _operation(connection: Connection[Any]) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE scrape_runs
                    SET is_current = FALSE
                    WHERE company_website_url = %s AND is_current = TRUE;
                    """,
                    (company_website_url,),
                )
                cursor.execute(
                    """
                    UPDATE scrape_runs
                    SET is_current = TRUE
                    WHERE company_website_url = %s AND scrape_run_id = %s;
                    """,
                    (company_website_url, scrape_run_id),
                )
                if cursor.rowcount != 1:
                    raise RuntimeError("Unable to mark scrape run as current.")

                cursor.execute(
                    """
                    UPDATE companies
                    SET scraped_at = (
                        SELECT scraped_at
                        FROM scrape_runs
                        WHERE scrape_run_id = %s
                    )
                    WHERE company_website_url = %s;
                    """,
                    (scrape_run_id, company_website_url),
                )

        self._execute_write(_operation)

    def get_current_company_overview(
        self,
        *,
        company_website_url: str,
        limit_per_sort: int,
        include_most_relevant: bool,
    ) -> CompanyReviewOverview | None:
        if limit_per_sort == 0 or limit_per_sort < -1:
            raise ValueError("limit_per_sort must be -1 or >= 1")

        return self._execute_read(
            lambda connection: self._get_current_company_overview_with_connection(
                connection=connection,
                company_website_url=company_website_url,
                limit_per_sort=limit_per_sort,
                include_most_relevant=include_most_relevant,
            )
        )

    def _get_current_company_overview_with_connection(
        self,
        *,
        connection: Connection[Any],
        company_website_url: str,
        limit_per_sort: int,
        include_most_relevant: bool,
    ) -> CompanyReviewOverview | None:
        """Execute the multi-join overview query and assemble the CompanyReviewOverview model."""
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT
                    c.company_website_url,
                    c.normalized_website_domain,
                    r.scrape_run_id,
                    r.scraped_at
                FROM companies c
                JOIN scrape_runs r
                  ON c.company_website_url = r.company_website_url
                WHERE c.company_website_url = %s
                  AND r.is_current = TRUE
                ORDER BY r.scraped_at DESC
                LIMIT 1;
                """,
                (company_website_url,),
            )
            current_run_row = cursor.fetchone()
            if current_run_row is None:
                return None

            scrape_run_id = str(current_run_row["scrape_run_id"])
            cursor.execute(
                """
                SELECT
                    provider,
                    place_id,
                    data_id,
                    name,
                    address,
                    website_domain,
                    rating,
                    reviews_count,
                    raw_payload
                FROM places
                WHERE scrape_run_id = %s
                  AND is_deleted = FALSE
                ORDER BY provider ASC, name ASC NULLS LAST, place_id ASC;
                """,
                (scrape_run_id,),
            )
            place_rows = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    provider,
                    place_id,
                    star_1,
                    star_2,
                    star_3,
                    star_4,
                    star_5,
                    total_reviews,
                    scraped_at,
                    raw_payload
                FROM review_histograms
                WHERE scrape_run_id = %s;
                """,
                (scrape_run_id,),
            )
            histogram_rows = cursor.fetchall()
            histogram_by_place: dict[tuple[str, str], ReviewHistogram] = {}
            for row in histogram_rows:
                histogram_by_place[(row["provider"], row["place_id"])] = ReviewHistogram(
                    provider=row["provider"],
                    place_id=row["place_id"],
                    star_1=row["star_1"],
                    star_2=row["star_2"],
                    star_3=row["star_3"],
                    star_4=row["star_4"],
                    star_5=row["star_5"],
                    total_reviews=row["total_reviews"],
                    scraped_at=row["scraped_at"],
                    raw_payload=row["raw_payload"] or {},
                )

            requested_sort_values = [
                ReviewSortOrder.newest.value,
                ReviewSortOrder.best.value,
                ReviewSortOrder.worst.value,
            ]
            if include_most_relevant:
                requested_sort_values.append(ReviewSortOrder.most_relevant.value)

            cursor.execute(
                """
                SELECT
                    provider,
                    place_id,
                    data_id,
                    review_id,
                    sort_order,
                    sort_rank,
                    author_name,
                    author_contributor_id,
                    rating,
                    text,
                    translated_text,
                    likes,
                    written_at,
                    source,
                    review_link,
                    scraped_at,
                    is_deleted,
                    raw_payload
                FROM reviews
                WHERE scrape_run_id = %s
                  AND is_deleted = FALSE
                  AND sort_order = ANY(%s)
                ORDER BY provider ASC, place_id ASC, sort_order ASC, sort_rank ASC;
                """,
                (scrape_run_id, requested_sort_values),
            )
            review_rows = cursor.fetchall()

        reviews_by_key: dict[tuple[str, str, ReviewSortOrder], list[ReviewRecord]] = {}
        for row in review_rows:
            sort_order = ReviewSortOrder(row["sort_order"])
            key = (row["provider"], row["place_id"], sort_order)
            bucket = reviews_by_key.setdefault(key, [])
            if limit_per_sort != -1 and len(bucket) >= limit_per_sort:
                continue

            bucket.append(
                ReviewRecord(
                    provider=row["provider"],
                    place_id=row["place_id"],
                    data_id=row["data_id"],
                    review_id=row["review_id"],
                    sort_order=sort_order,
                    sort_rank=row["sort_rank"],
                    author_name=row["author_name"],
                    author_contributor_id=row["author_contributor_id"],
                    rating=row["rating"],
                    text=row["text"],
                    translated_text=row["translated_text"],
                    likes=row["likes"],
                    written_at=row["written_at"],
                    source=row["source"],
                    review_link=row["review_link"],
                    scraped_at=row["scraped_at"],
                    is_deleted=row["is_deleted"],
                    raw_payload=row["raw_payload"] or {},
                )
            )

        locations: list[LocationOverview] = []
        for place_row in place_rows:
            provider = place_row["provider"]
            place_id = place_row["place_id"]
            key_prefix = (provider, place_id)

            newest_reviews = reviews_by_key.get((*key_prefix, ReviewSortOrder.newest), [])
            best_reviews = reviews_by_key.get((*key_prefix, ReviewSortOrder.best), [])
            worst_reviews = reviews_by_key.get((*key_prefix, ReviewSortOrder.worst), [])
            most_relevant_reviews = None
            if include_most_relevant:
                most_relevant_reviews = reviews_by_key.get((*key_prefix, ReviewSortOrder.most_relevant), [])

            locations.append(
                LocationOverview(
                    provider=provider,
                    place_id=place_id,
                    data_id=place_row["data_id"],
                    name=place_row["name"],
                    address=place_row["address"],
                    website_domain=place_row["website_domain"],
                    rating=place_row["rating"],
                    reviews_count=place_row["reviews_count"],
                    raw_payload=place_row["raw_payload"] or {},
                    histogram=histogram_by_place.get((provider, place_id)),
                    newest_reviews=newest_reviews,
                    best_reviews=best_reviews,
                    worst_reviews=worst_reviews,
                    most_relevant_reviews=most_relevant_reviews,
                )
            )

        return CompanyReviewOverview(
            company_website_url=current_run_row["company_website_url"],
            normalized_website_domain=current_run_row["normalized_website_domain"],
            scraped_at=current_run_row["scraped_at"],
            locations=locations,
        )

    def get_current_place_by_data_id(self, *, data_id: str) -> DiscoveredPlace | None:
        """Look up a place by data_id within any current scrape run."""
        def _operation(connection: Connection[Any]) -> DiscoveredPlace | None:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        p.scrape_run_id,
                        p.provider,
                        p.place_id,
                        p.data_id,
                        p.company_website_url,
                        p.name,
                        p.address,
                        p.website_domain,
                        p.rating,
                        p.reviews_count,
                        p.scraped_at,
                        p.is_deleted,
                        p.raw_payload
                    FROM places p
                    JOIN scrape_runs r
                      ON p.scrape_run_id = r.scrape_run_id
                    WHERE p.data_id = %s
                      AND p.is_deleted = FALSE
                      AND r.is_current = TRUE
                    ORDER BY r.scraped_at DESC
                    LIMIT 1;
                    """,
                    (data_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                return DiscoveredPlace(
                    provider=row["provider"],
                    place_id=row["place_id"],
                    data_id=row["data_id"],
                    company_website_url=row["company_website_url"],
                    name=row["name"],
                    address=row["address"],
                    website_domain=row["website_domain"],
                    rating=row["rating"],
                    reviews_count=row["reviews_count"],
                    scraped_at=row["scraped_at"],
                    is_deleted=row["is_deleted"],
                    raw_payload=row["raw_payload"] or {},
                )

        return self._execute_read(_operation)

    def get_reviews_for_place_sort(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
        sort_order: ReviewSortOrder,
        limit: int,
    ) -> list[ReviewRecord]:
        def _operation(connection: Connection[Any]) -> list[ReviewRecord]:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        provider,
                        place_id,
                        data_id,
                        review_id,
                        sort_order,
                        sort_rank,
                        author_name,
                        author_contributor_id,
                        rating,
                        text,
                        translated_text,
                        likes,
                        written_at,
                        source,
                        review_link,
                        scraped_at,
                        is_deleted,
                        raw_payload
                    FROM reviews
                    WHERE scrape_run_id = %s
                      AND provider = %s
                      AND place_id = %s
                      AND sort_order = %s
                      AND is_deleted = FALSE
                    ORDER BY sort_rank ASC
                    LIMIT %s;
                    """,
                    (scrape_run_id, provider, place_id, sort_order.value, limit),
                )
                return [
                    ReviewRecord(
                        provider=row["provider"],
                        place_id=row["place_id"],
                        data_id=row["data_id"],
                        review_id=row["review_id"],
                        sort_order=ReviewSortOrder(row["sort_order"]),
                        sort_rank=row["sort_rank"],
                        author_name=row["author_name"],
                        author_contributor_id=row["author_contributor_id"],
                        rating=row["rating"],
                        text=row["text"],
                        translated_text=row["translated_text"],
                        likes=row["likes"],
                        written_at=row["written_at"],
                        source=row["source"],
                        review_link=row["review_link"],
                        scraped_at=row["scraped_at"],
                        is_deleted=row["is_deleted"],
                        raw_payload=row["raw_payload"] or {},
                    )
                    for row in cursor.fetchall()
                ]

        return self._execute_read(_operation)

    def upsert_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        """Insert or update review rows for a run, preserving other sort orders."""
        if not reviews:
            return 0

        def _operation(connection: Connection[Any]) -> int:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO reviews (
                        scrape_run_id,
                        provider,
                        place_id,
                        data_id,
                        review_id,
                        sort_order,
                        sort_rank,
                        author_name,
                        author_contributor_id,
                        rating,
                        text,
                        translated_text,
                        likes,
                        written_at,
                        source,
                        review_link,
                        scraped_at,
                        is_deleted,
                        raw_payload
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (scrape_run_id, provider, place_id, sort_order, review_id)
                    DO UPDATE SET
                        sort_rank = EXCLUDED.sort_rank,
                        author_name = EXCLUDED.author_name,
                        author_contributor_id = EXCLUDED.author_contributor_id,
                        rating = EXCLUDED.rating,
                        text = EXCLUDED.text,
                        translated_text = EXCLUDED.translated_text,
                        likes = EXCLUDED.likes,
                        written_at = EXCLUDED.written_at,
                        source = EXCLUDED.source,
                        review_link = EXCLUDED.review_link,
                        scraped_at = EXCLUDED.scraped_at,
                        is_deleted = EXCLUDED.is_deleted,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    [
                        (
                            scrape_run_id,
                            review.provider,
                            review.place_id,
                            review.data_id,
                            review.review_id,
                            review.sort_order.value,
                            review.sort_rank,
                            review.author_name,
                            review.author_contributor_id,
                            review.rating,
                            review.text,
                            review.translated_text,
                            review.likes,
                            review.written_at,
                            review.source,
                            review.review_link,
                            review.scraped_at,
                            review.is_deleted,
                            Jsonb(review.raw_payload),
                        )
                        for review in reviews
                    ],
                )
                return len(reviews)

        row_count = self._execute_write(_operation)
        self._logger.info("repository_reviews_upserted scrape_run_id=%s count=%s", scrape_run_id, row_count)
        return row_count

    def upsert_run_histogram(self, *, scrape_run_id: str, histogram: ReviewHistogram) -> None:
        """Insert or update the histogram row for a (run, provider, place) combination."""
        def _operation(connection: Connection[Any]) -> None:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO review_histograms (
                        scrape_run_id,
                        provider,
                        place_id,
                        star_1,
                        star_2,
                        star_3,
                        star_4,
                        star_5,
                        total_reviews,
                        scraped_at,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (scrape_run_id, provider, place_id)
                    DO UPDATE SET
                        star_1 = EXCLUDED.star_1,
                        star_2 = EXCLUDED.star_2,
                        star_3 = EXCLUDED.star_3,
                        star_4 = EXCLUDED.star_4,
                        star_5 = EXCLUDED.star_5,
                        total_reviews = EXCLUDED.total_reviews,
                        scraped_at = EXCLUDED.scraped_at,
                        raw_payload = EXCLUDED.raw_payload;
                    """,
                    (
                        scrape_run_id,
                        histogram.provider,
                        histogram.place_id,
                        histogram.star_1,
                        histogram.star_2,
                        histogram.star_3,
                        histogram.star_4,
                        histogram.star_5,
                        histogram.total_reviews,
                        histogram.scraped_at,
                        Jsonb(histogram.raw_payload),
                    ),
                )

        self._execute_write(_operation)
        self._logger.info(
            "repository_histogram_upserted scrape_run_id=%s provider=%s place_id=%s",
            scrape_run_id,
            histogram.provider,
            histogram.place_id,
        )

    def get_histogram_for_place(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
    ) -> ReviewHistogram | None:
        def _operation(connection: Connection[Any]) -> ReviewHistogram | None:
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        provider,
                        place_id,
                        star_1,
                        star_2,
                        star_3,
                        star_4,
                        star_5,
                        total_reviews,
                        scraped_at,
                        raw_payload
                    FROM review_histograms
                    WHERE scrape_run_id = %s
                      AND provider = %s
                      AND place_id = %s;
                    """,
                    (scrape_run_id, provider, place_id),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                return ReviewHistogram(
                    provider=row["provider"],
                    place_id=row["place_id"],
                    star_1=row["star_1"],
                    star_2=row["star_2"],
                    star_3=row["star_3"],
                    star_4=row["star_4"],
                    star_5=row["star_5"],
                    total_reviews=row["total_reviews"],
                    scraped_at=row["scraped_at"],
                    raw_payload=row["raw_payload"] or {},
                )

        return self._execute_read(_operation)

    def _execute_write(self, operation: Any) -> Any:
        """Run a write operation, reusing an ambient transaction connection if one is active."""
        active_connection = _active_connection.get()
        if active_connection is not None:
            return operation(active_connection)

        with self._pool.connection() as connection:
            try:
                result = operation(connection)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise

    def _execute_read(self, operation: Any) -> Any:
        """Run a read operation, reusing an ambient transaction connection if one is active."""
        active_connection = _active_connection.get()
        if active_connection is not None:
            return operation(active_connection)

        with self._pool.connection() as connection:
            return operation(connection)
