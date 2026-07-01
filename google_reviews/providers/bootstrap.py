"""Helpers for constructing provider clients from settings."""

from __future__ import annotations

import logging

import requests

from ..config import Settings, get_settings
from .base_provider import MapsProvider
from .searchapi_client import SearchApiClient
from .serpapi_client import SerpApiClient


def create_maps_provider_from_settings(
    *,
    settings: Settings | None = None,
    session: requests.Session | None = None,
    logger: logging.Logger | None = None,
) -> MapsProvider:
    """Create a provider client based on `settings.search_provider`."""

    resolved_settings = settings or get_settings()
    if resolved_settings.search_provider == "searchapi":
        return SearchApiClient.from_settings(
            settings=resolved_settings,
            session=session,
            logger=logger,
        )
    if resolved_settings.search_provider == "serpapi":
        return SerpApiClient.from_settings(
            settings=resolved_settings,
            session=session,
            logger=logger,
        )

    raise ValueError(f"Unsupported search provider: `{resolved_settings.search_provider}`")
