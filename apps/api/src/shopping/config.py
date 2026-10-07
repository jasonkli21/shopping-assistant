from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    environment: Literal["local", "staging", "production"] = "local"
    auth_mode: Literal["local", "firebase"] = "local"
    database_url: str = "postgresql+psycopg://shopping:shopping@localhost:5432/shopping"
    migration_database_url: str | None = None
    local_owner_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    firebase_project_id: str | None = Field(default=None, max_length=128)
    firebase_owner_uid: str | None = Field(default=None, max_length=128)
    personal_ai_url: str = "http://localhost:8080"
    personal_ai_mode: Literal["fake", "external"] = "fake"
    conversation_generation_timeout_seconds: int = Field(default=30, gt=0, le=120)
    conversation_max_concurrent_generations: int = Field(default=4, gt=0, le=32)
    search_provider: str = "fake"
    tavily_api_key: str | None = None
    cors_origins: str = "http://localhost:5173"
    db_pool_size: int = Field(default=2, ge=1, le=10)
    db_max_overflow: int = Field(default=0, ge=0, le=5)
    db_pool_timeout_seconds: int = Field(default=5, gt=0, le=30)
    db_connect_timeout_seconds: int = Field(default=5, gt=0, le=30)
    research_max_queries: int = Field(default=8, gt=0, le=20)
    research_max_candidates: int = Field(default=20, gt=0, le=100)
    research_max_results: int = Field(default=60, gt=0, le=200)
    research_max_results_per_query: int = Field(default=10, gt=0, le=20)
    research_max_attempts: int = Field(default=8, gt=0, le=20)
    research_max_products: int = Field(default=3, gt=0, le=5)
    research_max_sources_per_product: int = Field(default=4, gt=0, le=12)
    research_max_pages: int = Field(default=10, gt=0, le=30)
    research_max_total_bytes: int = Field(default=1_500_000, gt=0, le=10_000_000)
    research_max_ai_calls: int = Field(default=16, gt=0, le=60)
    research_max_output_chars: int = Field(default=16_000, gt=0, le=32_000)
    research_deadline_seconds: int = Field(default=60, gt=0, le=300)
    research_provider_timeout_seconds: int = Field(default=15, gt=0, le=60)
    research_max_concurrent_searches: int = Field(default=1, gt=0, le=16)
    research_max_concurrent_runs: int = Field(default=2, gt=0, le=16)

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    @model_validator(mode="after")
    def validate_deployment_security(self) -> "Settings":
        if self.environment == "local":
            if self.auth_mode != "local":
                raise ValueError("Local development must use AUTH_MODE=local")
            return self

        if self.auth_mode != "firebase":
            raise ValueError("Staging and production require AUTH_MODE=firebase")
        if not self.firebase_project_id or not self.firebase_owner_uid:
            raise ValueError(
                "FIREBASE_PROJECT_ID and FIREBASE_OWNER_UID are required outside local mode"
            )
        if not self.cors_origin_list or "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must contain exact origins and cannot contain '*'")
        for origin in self.cors_origin_list:
            parsed_origin = urlsplit(origin)
            if (
                parsed_origin.scheme != "https"
                or not parsed_origin.netloc
                or parsed_origin.path
                or parsed_origin.query
                or parsed_origin.fragment
                or parsed_origin.username
                or parsed_origin.password
            ):
                raise ValueError("CORS_ORIGINS must be exact HTTPS origins without paths")
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use SQLAlchemy's postgresql+psycopg form")
        try:
            sslmode = make_url(self.database_url).query.get("sslmode")
        except Exception:
            raise ValueError("DATABASE_URL is malformed") from None
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("DATABASE_URL must require TLS with sslmode=require or stronger")
        if self.environment == "production":
            if self.search_provider != "tavily" or not self.tavily_api_key:
                raise ValueError("Production requires SEARCH_PROVIDER=tavily and TAVILY_API_KEY")
            if self.personal_ai_mode != "external":
                raise ValueError("Production cannot use deterministic fake Personal AI responses")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
