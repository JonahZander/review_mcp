"""Unit tests for service orchestration behavior."""

from __future__ import annotations

from contextlib import AbstractContextManager, nullcontext
from datetime import UTC, datetime

from google_reviews.models.domain_models import (
    CompanyRecord,
    CompanyReviewOverview,
    DiscoveredPlace,
    LocationOverview,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
    ScrapeRun,
)
from google_reviews.providers.base_provider import MapsProvider
from google_reviews.services.company_review_service import CompanyReviewService
from google_reviews.storage.base_repository import ReviewsRepository


class FakeProvider(MapsProvider):
    def __init__(self, *, max_reviews_fetch_cap: int = 100) -> None:
        self.calls: list[str] = []
        self._max_reviews_fetch_cap = max_reviews_fetch_cap

    @property
    def provider_name(self) -> str:
        return "searchapi"

    @property
    def max_reviews_fetch_cap(self) -> int:
        return self._max_reviews_fetch_cap

    def discover_company_places(self, *, query: str) -> list[DiscoveredPlace]:
        self.calls.append("discover_company_places")
        now = datetime.now(tz=UTC)
        return [
            DiscoveredPlace(
                provider="searchapi",
                place_id="p-1",
                data_id="d-1",
                company_website_url=query,
                name="Aptiva Health",
                website_domain="aptivahealth.com",
                rating=4.9,
                reviews_count=120,
                scraped_at=now,
                raw_payload={"place_id": "p-1", "name": "Aptiva Health", "rating": 4.9, "reviews_count": 120},
            ),
            DiscoveredPlace(
                provider="searchapi",
                place_id="p-2",
                data_id="d-2",
                company_website_url=query,
                name="Wrong Domain",
                website_domain="other-company.com",
                scraped_at=now,
                raw_payload={"place_id": "p-2", "name": "Wrong Domain"},
            ),
        ]

    def retrieve_num_reviews(
        self,
        *,
        place: DiscoveredPlace,
        sort_order: ReviewSortOrder | None = None,
        num: int | None = None,
    ) -> list[ReviewRecord]:
        resolved_sort_order = sort_order or ReviewSortOrder.unspecified
        self.calls.append(f"retrieve_num_reviews:{place.place_id}:{resolved_sort_order.value}:{num}")
        now = datetime.now(tz=UTC)
        return [
            ReviewRecord(
                provider=place.provider,
                place_id=place.place_id,
                data_id=place.data_id,
                review_id=f"{resolved_sort_order.value}-1",
                sort_order=resolved_sort_order,
                sort_rank=1,
                rating=5,
                text=f"{resolved_sort_order.value} review",
                scraped_at=now,
                raw_payload={
                    "review_id": f"{resolved_sort_order.value}-1",
                    "sort_order": resolved_sort_order.value,
                    "rating": 5,
                    "text": f"{resolved_sort_order.value} review",
                },
            )
        ]

    def retrieve_review_histogram(self, *, place: DiscoveredPlace) -> ReviewHistogram | None:
        self.calls.append(f"retrieve_review_histogram:{place.place_id}")
        now = datetime.now(tz=UTC)
        return ReviewHistogram(
            provider=place.provider,
            place_id=place.place_id,
            star_1=1,
            star_2=2,
            star_3=3,
            star_4=4,
            star_5=5,
            total_reviews=15,
            scraped_at=now,
            raw_payload={"star_1": 1, "star_2": 2, "star_3": 3, "star_4": 4, "star_5": 5, "total_reviews": 15},
        )


class FakeRepository(ReviewsRepository):
    def __init__(self) -> None:
        self.company: CompanyRecord | None = None
        self.current_run: ScrapeRun | None = None
        self.cached_overview: CompanyReviewOverview | None = None
        self.places: list[DiscoveredPlace] = []
        self.reviews: list[ReviewRecord] = []
        self.histograms: list[ReviewHistogram] = []
        self.current_run_id: str | None = None

    def initialize_schema(self) -> None:
        return

    def transaction(self) -> AbstractContextManager[None]:
        return nullcontext()

    def upsert_company(self, company: CompanyRecord) -> None:
        self.company = company

    def start_scrape_run(
        self,
        *,
        company_website_url: str,
        include_most_relevant: bool,
        requested_limit_per_sort: int,
        scraped_at: datetime,
    ) -> ScrapeRun:
        self.current_run = ScrapeRun(
            scrape_run_id="run-1",
            company_website_url=company_website_url,
            scraped_at=scraped_at,
            include_most_relevant=include_most_relevant,
            requested_limit_per_sort=requested_limit_per_sort,
            is_current=False,
        )
        return self.current_run

    def get_current_scrape_run(self, *, company_website_url: str) -> ScrapeRun | None:
        if self.current_run is None:
            return None
        if self.current_run.company_website_url != company_website_url:
            return None
        return self.current_run

    def replace_run_places(self, *, scrape_run_id: str, places: list[DiscoveredPlace]) -> int:
        self.places = list(places)
        return len(places)

    def replace_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        self.reviews = list(reviews)
        return len(reviews)

    def replace_run_histograms(self, *, scrape_run_id: str, histograms: list[ReviewHistogram]) -> int:
        self.histograms = list(histograms)
        return len(histograms)

    def set_scrape_run_current(self, *, company_website_url: str, scrape_run_id: str) -> None:
        self.current_run_id = scrape_run_id

    def get_current_company_overview(
        self,
        *,
        company_website_url: str,
        limit_per_sort: int,
        include_most_relevant: bool,
    ) -> CompanyReviewOverview | None:
        if self.cached_overview is not None:
            return self.cached_overview

        assert self.company is not None
        histogram = self.histograms[0] if self.histograms else None

        by_sort: dict[ReviewSortOrder, list[ReviewRecord]] = {
            sort_order: [review for review in self.reviews if review.sort_order == sort_order]
            for sort_order in ReviewSortOrder
        }
        def _limit(records: list[ReviewRecord]) -> list[ReviewRecord]:
            if limit_per_sort == -1:
                return records
            return records[:limit_per_sort]

        place_rating = None
        place_reviews_count = None
        for p in self.places:
            if p.place_id == "p-1":
                place_rating = p.rating
                place_reviews_count = p.reviews_count
                break

        location = LocationOverview(
            provider="searchapi",
            place_id="p-1",
            data_id="d-1",
            name="Aptiva Health",
            website_domain="aptivahealth.com",
            rating=place_rating,
            reviews_count=place_reviews_count,
            histogram=histogram,
            newest_reviews=_limit(by_sort[ReviewSortOrder.newest]),
            best_reviews=_limit(by_sort[ReviewSortOrder.best]),
            worst_reviews=_limit(by_sort[ReviewSortOrder.worst]),
            most_relevant_reviews=(
                _limit(by_sort[ReviewSortOrder.most_relevant]) if include_most_relevant else None
            ),
        )
        return CompanyReviewOverview(
            company_website_url=self.company.company_website_url,
            normalized_website_domain=self.company.normalized_website_domain,
            scraped_at=self.company.scraped_at,
            locations=[location],
        )

    def get_current_place_by_data_id(self, *, data_id: str) -> DiscoveredPlace | None:
        for place in self.places:
            if place.data_id == data_id:
                return place
        return None

    def get_reviews_for_place_sort(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
        sort_order: ReviewSortOrder,
        limit: int,
    ) -> list[ReviewRecord]:
        matched = [
            r for r in self.reviews
            if r.provider == provider and r.place_id == place_id and r.sort_order == sort_order
        ]
        return matched if limit == -1 else matched[:limit]

    def upsert_run_reviews(self, *, scrape_run_id: str, reviews: list[ReviewRecord]) -> int:
        self.reviews.extend(reviews)
        return len(reviews)

    def upsert_run_histogram(self, *, scrape_run_id: str, histogram: ReviewHistogram) -> None:
        self.histograms.append(histogram)

    def get_histogram_for_place(
        self,
        *,
        scrape_run_id: str,
        provider: str,
        place_id: str,
    ) -> ReviewHistogram | None:
        for h in self.histograms:
            if h.provider == provider and h.place_id == place_id:
                return h
        return None


def test_search_company_places_filters_by_domain() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    result = service.search_company_places(company_url="https://aptivahealth.com/path?x=1")

    assert "aptivahealth.com" in result
    assert len(repository.places) == 1
    assert repository.places[0].place_id == "p-1"
    assert "discover_company_places" in provider.calls


def test_search_company_places_uses_cache_when_run_exists() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    now = datetime.now(tz=UTC)

    repository.current_run = ScrapeRun(
        scrape_run_id="run-cached",
        company_website_url="https://aptivahealth.com",
        scraped_at=now,
        include_most_relevant=True,
        requested_limit_per_sort=20,
        is_current=True,
    )
    repository.cached_overview = CompanyReviewOverview(
        company_website_url="https://aptivahealth.com",
        normalized_website_domain="aptivahealth.com",
        scraped_at=now,
        locations=[
            LocationOverview(
                provider="searchapi",
                place_id="p-1",
                data_id="d-1",
                name="Aptiva Health",
                website_domain="aptivahealth.com",
                rating=4.9,
                reviews_count=120,
            ),
        ],
    )

    service = CompanyReviewService(provider=provider, repository=repository)
    result = service.search_company_places(company_url="aptivahealth.com")

    assert "p-1" in result
    assert provider.calls == []


def test_get_company_overview_discovers_and_fetches_reviews() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    result = service.get_company_overview(
        company_url="aptivahealth.com",
        max_companies=5,
        max_reviews_per_sort=20,
    )

    assert "aptivahealth.com" in result
    assert "discover_company_places" in provider.calls
    review_calls = [c for c in provider.calls if c.startswith("retrieve_num_reviews:")]
    assert len(review_calls) == 4


def test_rating_and_reviews_count_survive_cache_round_trip() -> None:
    """rating and reviews_count should be preserved when reading from cache."""
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")

    assert len(repository.places) == 1
    assert repository.places[0].rating == 4.9
    assert repository.places[0].reviews_count == 120

    result = service.search_company_places(company_url="https://aptivahealth.com")

    assert "rating: 4.9" in result
    assert "reviews_count: 120" in result
    assert provider.calls.count("discover_company_places") == 1


def test_location_to_discovered_place_preserves_rating_and_reviews_count() -> None:
    """_location_to_discovered_place must propagate rating and reviews_count."""
    from google_reviews.services.company_review_service import _location_to_discovered_place

    now = datetime.now(tz=UTC)
    loc = LocationOverview(
        provider="serpapi",
        place_id="p-1",
        data_id="d-1",
        name="Test Place",
        website_domain="test.com",
        rating=4.5,
        reviews_count=42,
    )
    place = _location_to_discovered_place(loc, "https://test.com", now)

    assert place.rating == 4.5
    assert place.reviews_count == 42
    assert place.name == "Test Place"


def test_location_to_discovered_place_handles_none_rating() -> None:
    """_location_to_discovered_place must handle None rating/reviews_count gracefully."""
    from google_reviews.services.company_review_service import _location_to_discovered_place

    now = datetime.now(tz=UTC)
    loc = LocationOverview(
        provider="serpapi",
        place_id="p-1",
        data_id="d-1",
        name="Test Place",
        website_domain="test.com",
    )
    place = _location_to_discovered_place(loc, "https://test.com", now)

    assert place.rating is None
    assert place.reviews_count is None


class NoneHistogramProvider(FakeProvider):
    """Provider that always returns None for histograms."""

    def retrieve_review_histogram(self, *, place: DiscoveredPlace) -> ReviewHistogram | None:
        self.calls.append(f"retrieve_review_histogram:{place.place_id}")
        return None


def test_get_company_overview_handles_none_histogram_gracefully() -> None:
    """get_company_overview must not crash when histogram is None."""
    provider = NoneHistogramProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    result = service.get_company_overview(
        company_url="aptivahealth.com",
        max_companies=5,
        max_reviews_per_sort=20,
    )

    assert "aptivahealth.com" in result
    assert "[Histogram]" not in result


def test_get_place_reviews_handles_none_histogram_gracefully() -> None:
    """get_place_reviews must not crash when histogram is None."""
    provider = NoneHistogramProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")

    result = service.get_place_reviews(data_id="d-1", num_reviews=5)

    assert "review_id:" in result
    assert "[Histogram]" not in result


def test_company_record_raw_payload_populated() -> None:
    """CompanyRecord raw_payload should contain discovery metadata."""
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")

    assert repository.company is not None
    payload = repository.company.raw_payload
    assert payload["discovery_provider"] == "searchapi"
    assert payload["discovery_query"] == "aptivahealth.com"
    assert payload["places_discovered"] == 1
    assert "p-1" in payload["place_ids"]


# ------------------------------------------------------------------
# Raw (structured) output method tests
# ------------------------------------------------------------------


def test_search_company_places_raw_returns_structured_places() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    result = service.search_company_places_raw(company_url="https://aptivahealth.com")

    assert "places" in result
    assert len(result["places"]) == 1
    place = result["places"][0]
    # raw returns only the provider's raw_payload
    assert place == {"place_id": "p-1", "name": "Aptiva Health", "rating": 4.9, "reviews_count": 120}


def test_get_place_reviews_raw_returns_place_and_reviews() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")
    result = service.get_place_reviews_raw(data_id="d-1", num_reviews=5, sort_order="best")

    assert "place" in result
    assert result["place"]["place_id"] == "p-1"
    assert result["place"]["rating"] == 4.9

    assert "reviews" in result
    assert len(result["reviews"]) >= 1
    assert result["reviews"][0]["sort_order"] == "best"
    assert result["reviews"][0]["review_id"] == "best-1"


def test_get_place_reviews_raw_includes_histogram_when_available() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")
    result = service.get_place_reviews_raw(data_id="d-1", num_reviews=5)

    assert "histogram" in result
    # raw returns only the provider's raw_payload
    assert result["histogram"] == {"star_1": 1, "star_2": 2, "star_3": 3, "star_4": 4, "star_5": 5, "total_reviews": 15}


def test_get_place_reviews_raw_omits_histogram_when_none() -> None:
    provider = NoneHistogramProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    service.search_company_places(company_url="https://aptivahealth.com")
    result = service.get_place_reviews_raw(data_id="d-1", num_reviews=5)

    assert "place" in result
    assert "reviews" in result
    assert "histogram" not in result


def test_get_company_overview_raw_returns_structured_locations() -> None:
    provider = FakeProvider()
    repository = FakeRepository()
    service = CompanyReviewService(provider=provider, repository=repository)

    result = service.get_company_overview_raw(
        company_url="aptivahealth.com",
        max_companies=5,
        max_reviews_per_sort=20,
    )

    assert result["company_website_url"] == "https://aptivahealth.com"
    assert result["normalized_website_domain"] == "aptivahealth.com"
    assert len(result["locations"]) == 1

    loc = result["locations"][0]
    # raw returns only the provider's raw_payload
    assert loc["place"] == {"place_id": "p-1", "name": "Aptiva Health", "rating": 4.9, "reviews_count": 120}
    assert "best" in loc["reviews"]
    assert "worst" in loc["reviews"]
    assert "newest" in loc["reviews"]
    assert "most_relevant" in loc["reviews"]
    assert "histogram" in loc
    assert loc["histogram"] == {"star_1": 1, "star_2": 2, "star_3": 3, "star_4": 4, "star_5": 5, "total_reviews": 15}
