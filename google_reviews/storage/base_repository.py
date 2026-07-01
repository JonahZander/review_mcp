"""Repository protocol definitions for storage adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from datetime import datetime

from ..models.domain_models import (
    CompanyRecord,
    CompanyReviewOverview,
    DiscoveredPlace,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
    ScrapeRun,
)


class ReviewsRepository(ABC):
    """Storage-agnostic repository interface used by services."""

    @abstractmethod
    def initialize_schema(self) -> None:
        """Ensure required persistence schema exists."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Create a transactional context for a unit of work."""

    @abstractmethod
    def upsert_company(self, company: CompanyRecord) -> None:
        """Upsert the canonical company record."""

    @abstractmethod
    def start_scrape_run(
        self,
        *,
        company_website_url: str,
        include_most_relevant: bool,
        requested_limit_per_sort: int,
        scraped_at: datetime,
    ) -> ScrapeRun:
        """Create a new scrape run for a company."""

    @abstractmethod
    def get_current_scrape_run(self, *, company_website_url: str) -> ScrapeRun | None:
        """Return the currently active run metadata for a company if it exists."""

    @abstractmethod
    def replace_run_places(self, *, scrape_run_id: str, places: list[DiscoveredPlace]) -> int:
        """Replace all places for one run."""

    @abstractmethod
    def replace_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        """Replace all reviews for one run."""

    @abstractmethod
    def replace_run_histograms(self, *, scrape_run_id: str, histograms: list[ReviewHistogram]) -> int:
        """Replace all histogram rows for one run."""

    @abstractmethod
    def set_scrape_run_current(self, *, company_website_url: str, scrape_run_id: str) -> None:
        """Mark a run as current and demote previous current run(s)."""

    @abstractmethod
    def get_current_company_overview(
        self,
        *,
        company_website_url: str,
        limit_per_sort: int,
        include_most_relevant: bool,
    ) -> CompanyReviewOverview | None:
        """Read company overview from the currently active run."""

    @abstractmethod
    def get_current_place_by_data_id(self, *, data_id: str) -> DiscoveredPlace | None:
        """Look up a place by data_id across current scrape runs."""

    @abstractmethod
    def get_reviews_for_place_sort(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
        sort_order: ReviewSortOrder,
        limit: int,
    ) -> list[ReviewRecord]:
        """Read reviews for one place and sort order from a specific run."""

    @abstractmethod
    def upsert_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        """Insert or update reviews for a run without deleting other sort orders."""

    @abstractmethod
    def upsert_run_histogram(self, *, scrape_run_id: str, histogram: ReviewHistogram) -> None:
        """Insert or update a histogram row for one place within a run."""

    @abstractmethod
    def get_histogram_for_place(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
    ) -> ReviewHistogram | None:
        """Read the histogram for one place from a specific run."""

    def close(self) -> None:  # noqa: B027 - intentional concrete no-op; see docstring
        """Release resources held by the repository (e.g. connection pool).

        Default no-op - override in concrete implementations that hold
        resources requiring explicit cleanup. Kept concrete (not abstract)
        so existing fakes and mocks require no changes.
        """
