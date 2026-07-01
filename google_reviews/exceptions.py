"""Custom exceptions for integration boundaries and provider failures."""

from typing import Any


class IntegrationError(Exception):
    """Base exception for this integration module."""


class ConfigurationError(IntegrationError):
    """Raised when configuration is missing or invalid."""


class ProviderError(IntegrationError):
    """Base exception for provider-level failures."""


class ProviderRetryableError(ProviderError):
    """Raised for transient provider errors that should be retried."""


class ProviderPermanentError(ProviderError):
    """Raised for provider errors that should not be retried."""


class ProviderAuthenticationError(ProviderPermanentError):
    """Raised when provider authentication fails."""


class ProviderResponseError(ProviderError):
    """Raised when provider responds with a non-success status or malformed payload."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.payload = payload


class PlaceNotFoundError(IntegrationError):
    """Raised when a place lookup fails because the place does not exist in the database."""

    def __init__(self, *, data_id: str) -> None:
        """Store data_id for downstream handling."""
        super().__init__(
            f"No place found in current scrape run for data_id=`{data_id}`. "
            "Run search_company_places first."
        )
        self.data_id = data_id
