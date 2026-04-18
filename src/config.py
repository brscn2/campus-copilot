"""Application configuration via Pydantic Settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Single source of truth for all configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "production"] = "development"

    # Database
    database_url: str = "postgresql+asyncpg://copilot:copilot@localhost:5432/campus_copilot"

    # AWS
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "eu-north-1"

    # Bedrock
    bedrock_region: str = "eu-north-1"
    bedrock_sonnet_model_id: str = "eu.anthropic.claude-sonnet-4-6"
    bedrock_haiku_model_id: str = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    bedrock_titan_embed_model_id: str = "amazon.titan-embed-text-v2:0"

    # Cognee
    cognee_api_key: str = ""
    cognee_api_url: str = "https://api.cognee.ai"
    cognee_llm_provider: str = "custom"

    # Google Calendar
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"

    # S3
    s3_bucket: str = "campus-copilot-demo"

    # Frontend
    frontend_url: str = "http://localhost:3000"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
