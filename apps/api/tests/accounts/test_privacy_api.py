import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from shopping.accounts.export import _safe_url, export_owner_data, purge_owner_data
from shopping.accounts.models import (
    FirebaseOwnerBinding,
    OwnerPrivacyEvent,
    OwnerPrivacyLifecycle,
)
from shopping.projects.models import ProjectRequirement, ShoppingProject

pytestmark = pytest.mark.db


def _create_project(client, title="Privacy review project"):
    response = client.post(
        "/projects",
        json={"title": title, "goal": "Find a compact desk", "requirements": []},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_export_uses_one_repeatable_read_snapshot(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    project_id = project["id"]

    with Session(engine) as exporter:
        exporter.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        assert (
            exporter.scalar(
                select(ShoppingProject.revision).where(ShoppingProject.id == project_id)
            )
            == 1
        )
        with Session(engine) as writer:
            writer.execute(
                text("UPDATE shopping_projects SET revision = 2 WHERE id = :project_id"),
                {"project_id": project_id},
            )
            writer.add(
                ProjectRequirement(
                    project_id=project_id,
                    kind="preference",
                    label="Added in revision two",
                    position=0,
                )
            )
            writer.commit()

        payload = json.loads(export_owner_data(exporter, owner["id"]))
        exported_project = payload["records"]["shopping_projects"][0]
        assert exported_project["revision"] == 1
        assert payload["records"].get("project_requirements", []) == []


def test_export_is_owner_scoped_and_redacts_url_credentials(project_api):
    client, owner, engine = project_api
    visible = _create_project(client, "Visible owner project")
    foreign_owner_id = uuid4()
    with Session(engine) as session:
        session.add(
            ShoppingProject(
                owner_id=foreign_owner_id,
                title="Foreign owner project",
                goal="Must not appear in export",
            )
        )
        session.commit()
        payload = json.loads(export_owner_data(session, owner["id"]))

    project_ids = {item["id"] for item in payload["records"]["shopping_projects"]}
    assert project_ids == {visible["id"]}
    assert "firebase_owner_bindings" not in payload["records"]
    assert _safe_url("https://private-user:private-pass@example.test/path") == (
        "https://example.test/path"
    )


def test_purge_reports_cascaded_rows_and_fences_later_writes(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    requirement = client.post(
        f"/projects/{project['id']}/requirements?expected_version={project['revision']}",
        json={"kind": "must_have", "label": "Narrow enough"},
    )
    assert requirement.status_code == 200, requirement.text
    with Session(engine) as session:
        session.add(FirebaseOwnerBinding(firebase_uid="privacy-test-uid", owner_id=owner["id"]))
        session.commit()

    response = client.delete("/account/data?confirm=DELETE_MY_DATA")
    assert response.status_code == 200, response.text
    counts = response.json()["deleted_records"]
    assert counts["shopping_projects"] == 1
    assert counts["project_requirements"] == 1
    assert counts["firebase_owner_bindings"] == 1

    with Session(engine) as session:
        lifecycle = session.get(OwnerPrivacyLifecycle, owner["id"])
        event = session.scalar(
            select(OwnerPrivacyEvent).where(OwnerPrivacyEvent.owner_id == owner["id"])
        )
        assert lifecycle.state == "purged"
        assert event.record_counts == counts
        assert session.get(FirebaseOwnerBinding, "privacy-test-uid") is None
        session.add(
            ShoppingProject(owner_id=owner["id"], title="Late write", goal="Must be rejected")
        )
        with pytest.raises(DBAPIError):
            session.flush()
        session.rollback()


def test_purge_waits_for_an_inflight_write_and_counts_it(project_api):
    client, owner, engine = project_api
    _create_project(client, "Existing project")
    writer = Session(engine)
    writer.add(
        ShoppingProject(owner_id=owner["id"], title="In-flight project", goal="Must be counted")
    )
    writer.flush()

    started = Event()

    def purge():
        with Session(engine) as session:
            started.set()
            return purge_owner_data(session, owner["id"], record_limit=None)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(purge)
            assert started.wait(timeout=2)
            with pytest.raises(TimeoutError):
                result.result(timeout=0.1)
            writer.commit()
            counts = result.result(timeout=5)
        assert counts["shopping_projects"] == 2
    finally:
        writer.close()


def test_http_limits_have_a_complete_operator_path(project_api):
    client, owner, engine = project_api
    rows = [
        {
            "id": uuid4(),
            "owner_id": owner["id"],
            "title": f"Project {index}",
            "goal": "Large owner export test",
        }
        for index in range(2_001)
    ]
    with Session(engine) as session:
        session.execute(insert(ShoppingProject), rows)
        session.commit()

    assert client.get("/account/export").status_code == 413
    assert client.delete("/account/data?confirm=DELETE_MY_DATA").status_code == 409

    with Session(engine) as session:
        payload = json.loads(
            export_owner_data(session, owner["id"], record_limit=None, max_bytes=None)
        )
        assert len(payload["records"]["shopping_projects"]) == 2_001
        session.rollback()
        counts = purge_owner_data(session, owner["id"], record_limit=None)
        assert counts["shopping_projects"] == 2_001
