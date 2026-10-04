from functools import lru_cache
from pathlib import Path
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
    search_provider: str = "fake"
    tavily_api_key: str | None = None
    brave_api_key: str | None = None
    cors_origins: str = "http://localhost:5173"
    research_max_queries: int = Field(default=8, gt=0)
    research_max_candidates: int = Field(default=20, gt=0)
    research_max_sources_per_product: int = Field(default=5, gt=0)

    model_config = SettingsConfigDict(env_file=REPOSITORY_ROOT / ".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
