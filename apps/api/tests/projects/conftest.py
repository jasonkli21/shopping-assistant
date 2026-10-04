from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from shopping.db.session import get_db
from shopping.main import app
from shopping.projects.dependencies import get_owner_id


@pytest.fixture
def project_api(db_engine: Engine) -> Iterator[tuple[TestClient, dict[str, UUID], Engine]]:
    current_owner = {"id": uuid4()}

    def override_db():
        with Session(db_engine) as session:
            yield session

    def override_owner() -> UUID:
        return current_owner["id"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_owner_id] = override_owner
    with TestClient(app) as client:
        try:
            yield client, current_owner, db_engine
        finally:
            app.dependency_overrides.clear()
