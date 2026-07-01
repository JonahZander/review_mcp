"""Helpers for constructing a fully-wired CompanyReviewService from settings."""

from __future__ import annotations

from ..config import Settings, get_settings
from ..providers.bootstrap import create_maps_provider_from_settings
from ..storage.bootstrap import create_postgres_repository_from_settings
from .company_review_service import CompanyReviewService


def create_review_service_from_settings(
    *,
    settings: Settings | None = None,
) -> CompanyReviewService:
    """Create a CompanyReviewService wired to provider + repository from .env settings.

    Intended to be called once at MCP server startup.
    """
    resolved = settings or get_settings()
    provider = create_maps_provider_from_settings(settings=resolved)
    repository, _ = create_postgres_repository_from_settings(settings=resolved)
    return CompanyReviewService(provider=provider, repository=repository)
