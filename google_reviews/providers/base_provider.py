"""Provider interfaces used by services."""

from abc import ABC, abstractmethod

from ..models.domain_models import DiscoveredPlace, ReviewHistogram, ReviewRecord, ReviewSortOrder


class MapsProvider(ABC):
    """Provider-agnostic interface consumed by service orchestration."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""

    @property
    @abstractmethod
    def max_reviews_fetch_cap(self) -> int:
        """Return the max count used when callers request `num=-1`."""

    @abstractmethod
    def discover_company_places(self, *, query: str) -> list[DiscoveredPlace]:
        """
        Discover places for an arbitrary query.

        Implementations should return provider-mapped place candidates without
        applying domain filtering or list limits.
        """

    @abstractmethod
    def retrieve_num_reviews(
        self,
        *,
        place: DiscoveredPlace,
        sort_order: ReviewSortOrder | None = None,
        num: int | None = None,
    ) -> list[ReviewRecord]:
        """
        Retrieve reviews for one place preserving provider ordering.

        `sort_order` semantics:
        - `None`: provider default ordering (do not set sort in provider API call)
        - specific value: explicit ordering request

        `num` semantics:
        - `None`: default to 20
        - positive integer: fetch that many reviews
        - `-1`: fetch up to provider-configured cap (`max_reviews_fetch_cap`)
        """

    @abstractmethod
    def retrieve_review_histogram(self, *, place: DiscoveredPlace) -> ReviewHistogram | None:
        """Retrieve a review histogram snapshot for one place."""
