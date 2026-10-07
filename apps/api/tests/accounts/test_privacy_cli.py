import sys
from uuid import uuid4

import pytest

from shopping.accounts.privacy import main


def test_operator_purge_requires_explicit_confirmation(monkeypatch, capsys):
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL",
        "postgresql+psycopg://operator:secret@db.example.test/shopping?sslmode=require",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["shopping-privacy", "--owner-id", str(uuid4()), "--mode", "purge"],
    )

    with pytest.raises(SystemExit) as raised:
        main()

    assert raised.value.code == 2
    assert "purge requires --confirm DELETE_MY_DATA" in capsys.readouterr().err


def test_operator_rejects_pooled_database_url_without_echoing_credentials(monkeypatch, capsys):
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL",
        "postgresql+psycopg://operator:secret%40pass@ep-test-pooler.db.example.test/"
        "shopping?sslmode=verify-full",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "shopping-privacy",
            "--owner-id",
            str(uuid4()),
            "--mode",
            "export",
            "--output",
            "/tmp/owner-export.json",
        ],
    )

    with pytest.raises(SystemExit) as raised:
        main()

    error = capsys.readouterr().err
    assert raised.value.code == 2
    assert "direct PostgreSQL endpoint with TLS" in error
    assert "secret" not in error
