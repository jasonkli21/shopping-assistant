from pathlib import Path

import pytest
from pydantic import ValidationError

from shopping.config import REPOSITORY_ROOT, Settings


def test_environment_file_is_independent_of_working_directory(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == REPOSITORY_ROOT / ".env"
    assert (REPOSITORY_ROOT / "README.md").is_file()


def test_environment_overrides_dotenv(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("RESEARCH_MAX_QUERIES=3\nCORS_ORIGINS=http://localhost:5173\n")
    monkeypatch.setenv("RESEARCH_MAX_QUERIES", "4")
    assert Settings(_env_file=env_file).research_max_queries == 4


def test_assistant_defaults_to_fake_with_bounded_generation_limits() -> None:
    settings = Settings(_env_file=None)
    assert settings.personal_ai_mode == "fake"
    assert settings.conversation_generation_timeout_seconds == 30
    assert settings.conversation_max_concurrent_generations == 4


@pytest.mark.parametrize("value", [0, -1])
def test_research_budgets_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_max_queries=value)


@pytest.mark.parametrize(
    "field", ["conversation_generation_timeout_seconds", "conversation_max_concurrent_generations"]
)
def test_assistant_generation_limits_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **{field: 0})
