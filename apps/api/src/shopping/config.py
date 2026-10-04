from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    """Typed application configuration loaded from environment variables."""

    environment: str = "local"
    database_url: str = "postgresql+psycopg://shopping:shopping@localhost:5432/shopping"
    local_owner_id: UUID = UUID("00000000-0000-4000-8000-000000000001")
    personal_ai_url: str = "http://localhost:8080"
    personal_ai_mode: Literal["fake", "external"] = "fake"
    conversation_generation_timeout_seconds: int = Field(default=30, gt=0, le=120)
    conversation_max_concurrent_generations: int = Field(default=4, gt=0, le=32)
    search_provider: str = "fake"
    tavily_api_key: str | None = None
    cors_origins: str = "http://localhost:5173"
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

    model_config = SettingsConfigDict(env_file=REPOSITORY_ROOT / ".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
