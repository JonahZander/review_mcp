"""Runtime configuration for the Google Reviews integration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed settings loaded from `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    search_provider: Literal["searchapi", "serpapi"] = "searchapi"

    searchapi_api_key: str | None = Field(default=None, description="API key for SearchAPI.")
    searchapi_base_url: str = Field(
        default="https://www.searchapi.io/api/v1/search",
        min_length=1,
        description="Base URL for SearchAPI requests.",
    )
    serpapi_api_key: str | None = Field(default=None, description="API key for SerpAPI.")
    serpapi_base_url: str = Field(
        default="https://serpapi.com/search",
        min_length=1,
        description="Base URL for SerpAPI requests.",
    )
    serpapi_no_cache: bool = Field(
        default=False,
        description="Whether SerpAPI maps discovery requests should disable cache.",
    )
    serpapi_use_no_cache: bool = Field(
        default=False,
        description="Whether SerpAPI map searches should pass no_cache=true.",
    )

    http_timeout_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
    retry_attempts: int = Field(default=5, ge=1, le=10)
    retry_min_seconds: float = Field(default=1.0, ge=0.1, le=30.0)
    retry_max_seconds: float = Field(default=20.0, ge=1.0, le=300.0)
    retry_jitter_seconds: float = Field(default=0.5, ge=0.0, le=5.0)
    reviews_fetch_all_cap: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum reviews per sort to fetch when request uses -1 (fetch all).",
    )

    postgres_dsn: str = Field(
        ...,
        min_length=1,
        description="PostgreSQL DSN for persistent review and company storage.",
    )
    log_level: str = Field(default="INFO", min_length=4, max_length=12)

    @model_validator(mode="after")
    def validate_provider_credentials(self) -> "Settings":
        """Ensure the API key for the configured provider is present."""
        if self.search_provider == "searchapi":
            if not self.searchapi_api_key:
                raise ValueError("searchapi_api_key is required when search_provider=searchapi")
            return self

        if not self.serpapi_api_key:
            raise ValueError("serpapi_api_key is required when search_provider=serpapi")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()  # type: ignore[call-arg]
