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


@pytest.mark.parametrize("value", [0, -1])
def test_research_budgets_must_be_positive(value: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, research_max_queries=value)
