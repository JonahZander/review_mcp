"""Retrying HTTP client for provider API calls."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin

import requests
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from ..exceptions import (
    ProviderAuthenticationError,
    ProviderPermanentError,
    ProviderResponseError,
    ProviderRetryableError,
)
from ..logging_config import get_logger

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504, 520, 522, 524}


class RetryingHttpClient:
    """
    Small atomic client that performs one provider request with retries.

    This wrapper intentionally owns only transport-level concerns:
    - timeout handling
    - retry/backoff behavior
    - status-to-exception mapping
    - JSON response parsing
    """

    def __init__(
        self,
        *,
        auth_value: str | None = None,
        api_key: str | None = None,
        auth_query_param_name: str = "api_key",
        service_name: str = "provider",
        base_url: str,
        timeout_seconds: float,
        retry_attempts: int,
        retry_min_seconds: float,
        retry_max_seconds: float,
        retry_jitter_seconds: float = 0.5,
        session: requests.Session | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        resolved_auth_value = auth_value if auth_value is not None else api_key
        if not resolved_auth_value:
            raise ValueError("Either auth_value or api_key must be provided.")

        self._auth_value = resolved_auth_value
        self._auth_query_param_name = auth_query_param_name
        self._service_name = service_name
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._retry_attempts = retry_attempts
        self._retry_min_seconds = retry_min_seconds
        self._retry_max_seconds = retry_max_seconds
        self._retry_jitter_seconds = retry_jitter_seconds
        self._session = session or requests.Session()
        self._logger = logger or get_logger(__name__)

    def perform_request_with_retry(
        self,
        *,
        params: Mapping[str, Any],
        endpoint: str = "",
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform a request and retry only on retryable failures."""

        request_url = self._build_url(endpoint)
        request_params = self._build_params(params)

        self._logger.info(
            "provider_http_request_started service=%s method=%s url=%s",
            self._service_name,
            method,
            request_url,
        )

        retryer = Retrying(
            stop=stop_after_attempt(self._retry_attempts),
            wait=wait_exponential_jitter(
                initial=self._retry_min_seconds,
                max=self._retry_max_seconds,
                jitter=self._retry_jitter_seconds,
            ),
            retry=retry_if_exception_type(ProviderRetryableError),
            before_sleep=before_sleep_log(self._logger, logging.WARNING),
            reraise=True,
        )

        for attempt in retryer:
            with attempt:
                payload = self._perform_request_once(
                    method=method,
                    url=request_url,
                    params=request_params,
                    headers=headers,
                )
                self._logger.info(
                    "provider_http_request_succeeded service=%s method=%s url=%s",
                    self._service_name,
                    method,
                    request_url,
                )
                return payload

        raise ProviderPermanentError("Retry loop ended without returning payload.")

    def _perform_request_once(
        self,
        *,
        method: str,
        url: str,
        params: Mapping[str, Any],
        headers: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        """Execute a single HTTP request; raise typed exceptions based on the outcome."""
        try:
            response = self._session.request(
                method=method,
                url=url,
                params=params,
                headers=dict(headers) if headers else None,
                timeout=self._timeout_seconds,
            )
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as exc:
            raise ProviderRetryableError(
                f"Transient network issue during {self._service_name} request."
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise ProviderPermanentError(
                f"Unexpected HTTP client failure during {self._service_name} request."
            ) from exc

        return self._parse_response(response)

    def _parse_response(self, response: requests.Response) -> dict[str, Any]:
        """Map an HTTP response to a parsed JSON payload or raise the appropriate typed exception."""
        status_code = response.status_code
        response_body = self._safe_response_text(response)

        if 200 <= status_code < 300:
            try:
                return response.json()
            except ValueError as exc:
                raise ProviderResponseError(
                    f"{self._service_name} returned non-JSON payload for successful response.",
                    status_code=status_code,
                    response_body=response_body,
                ) from exc

        if status_code in (401, 403):
            raise ProviderAuthenticationError(
                f"{self._service_name} authentication failed with status code {status_code}."
            )

        if status_code in RETRYABLE_STATUS_CODES:
            raise ProviderRetryableError(
                f"{self._service_name} returned retryable status code {status_code}. "
                f"Body: {response_body}"
            )

        raise ProviderResponseError(
            f"{self._service_name} returned non-retryable status code {status_code}.",
            status_code=status_code,
            response_body=response_body,
        )

    def _build_url(self, endpoint: str) -> str:
        """Join base URL with an optional path segment."""
        if not endpoint:
            return self._base_url

        return urljoin(self._base_url.rstrip("/") + "/", endpoint.lstrip("/"))

    def _build_params(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Merge caller-supplied params with the auth credential, dropping None values."""
        request_params = {key: value for key, value in params.items() if value is not None}
        request_params[self._auth_query_param_name] = self._auth_value
        return request_params

    @staticmethod
    def _safe_response_text(response: requests.Response, max_chars: int = 2_000) -> str:
        """Return response text truncated to at most max_chars characters."""
        if not response.text:
            return ""

        if len(response.text) <= max_chars:
            return response.text

        return f"{response.text[:max_chars]}...<truncated>"

