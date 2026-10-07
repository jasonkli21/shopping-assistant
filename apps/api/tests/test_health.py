import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from shopping.accounts.models import FirebaseOwnerBinding
from shopping.api import router as api_router
from shopping.main import app


def test_health() -> None:
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _ReadinessConnection:
    def __init__(self, applied_revision="head", owner_id=None):
        self.applied_revision = applied_revision
        self.owner_id = owner_id

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def scalar(self, statement):
        if "alembic_version" in str(statement):
            return self.applied_revision
        return self.owner_id


class _ReadinessEngine:
    def __init__(self, connection):
        self.connection_value = connection

    def connect(self):
        return self.connection_value


def _mock_migration_head(monkeypatch):
    class _ScriptDirectory:
        @staticmethod
        def from_config(_config):
            return _ScriptDirectory()

        @staticmethod
        def get_current_head():
            return "head"

    monkeypatch.setattr(api_router, "ScriptDirectory", _ScriptDirectory)


def test_readiness_rejects_outdated_schema(monkeypatch) -> None:
    _mock_migration_head(monkeypatch)
    monkeypatch.setattr(api_router, "engine", _ReadinessEngine(_ReadinessConnection("old")))
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "schema_not_ready"


@pytest.mark.db
def test_readiness_accepts_migrated_schema_and_configured_owner_binding(project_api, monkeypatch):
    client, owner, engine = project_api
    monkeypatch.setattr(api_router, "engine", engine)
    monkeypatch.setattr(
        api_router,
        "get_settings",
        lambda: type(
            "SettingsStub",
            (),
            {
                "auth_mode": "firebase",
                "firebase_owner_uid": "configured-owner",
                "local_owner_id": owner["id"],
            },
        )(),
    )
    with Session(engine) as session:
        session.add(FirebaseOwnerBinding(firebase_uid="configured-owner", owner_id=owner["id"]))
        session.commit()

    ready = client.get("/ready")
    assert ready.status_code == 200, ready.text
    assert ready.json() == {"status": "ready"}

    with Session(engine) as session:
        session.query(FirebaseOwnerBinding).delete()
        session.commit()
    unavailable = client.get("/ready")
    assert unavailable.status_code == 503
    assert unavailable.json()["error"]["code"] == "owner_binding_not_ready"
