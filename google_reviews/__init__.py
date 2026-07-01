"""Reusable Google Reviews integration primitives."""

from .config import Settings, get_settings
from .exceptions import (
    ConfigurationError,
    IntegrationError,
    ProviderAuthenticationError,
    ProviderError,
    ProviderPermanentError,
    ProviderResponseError,
    ProviderRetryableError,
)
from .models.domain_models import (
    CompanyReviewOverview,
    CompanyReviewRequest,
    DiscoveredPlace,
    ReviewHistogram,
    ReviewRecord,
    ReviewSortOrder,
)
from .providers import (
    RetryingHttpClient,
    SearchApiClient,
    SerpApiClient,
    create_maps_provider_from_settings,
)
from .services import CompanyReviewService
from .storage import (
    PostgresReviewsRepository,
    PsycopgConnectionPool,
    ReviewsRepository,
    create_postgres_repository,
    create_postgres_repository_from_settings,
)

__all__ = [
    "CompanyReviewOverview",
    "CompanyReviewRequest",
    "ConfigurationError",
    "DiscoveredPlace",
    "IntegrationError",
    "PostgresReviewsRepository",
    "ProviderAuthenticationError",
    "ProviderError",
    "ProviderPermanentError",
    "ProviderResponseError",
    "ProviderRetryableError",
    "PsycopgConnectionPool",
    "ReviewHistogram",
    "ReviewRecord",
    "ReviewSortOrder",
    "RetryingHttpClient",
    "ReviewsRepository",
    "SearchApiClient",
    "SerpApiClient",
    "Settings",
    "create_maps_provider_from_settings",
    "create_postgres_repository",
    "create_postgres_repository_from_settings",
    "CompanyReviewService",
    "get_settings",
]
