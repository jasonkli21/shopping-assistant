from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.db


def _create_project(client, *, title="Vacuum for apartment", goal="Find a pet-hair vacuum"):
    return client.post(
        "/projects",
        json={
            "title": title,
            "goal": goal,
            "budget_maximum": "400.00",
            "budget_currency": "USD",
            "requirements": [
                {"kind": "must_have", "label": "Works well on pet hair"},
                {
                    "kind": "preference",
                    "label": "Easy to carry",
                    "detail": "Under 8 pounds is ideal",
                },
            ],
        },
    )


def _error(response, status_code, code):
    assert response.status_code == status_code
    payload = response.json()
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == code
    assert payload["error"]["request_id"]
    return payload["error"]


def test_create_reload_patch_and_requirement_reorder_is_durable(project_api):
    client, _owner, _engine = project_api
    created = _create_project(client)
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["revision"] == 1
    assert project["budget_maximum"] == "400.00"
    assert [item["position"] for item in project["requirements"]] == [0, 1]
    requirement_ids = [item["id"] for item in project["requirements"]]

    reordered = client.patch(
        f"/projects/{project['id']}/requirements/{requirement_ids[1]}",
        json={"expected_version": 1, "position": 0},
    )
    assert reordered.status_code == 200
    assert reordered.json()["revision"] == 2
    assert reordered.json()["requirements"][0]["id"] == requirement_ids[1]

    after_reload = client.get(f"/projects/{project['id']}")
    assert after_reload.status_code == 200
    assert after_reload.json()["requirements"][0]["id"] == requirement_ids[1]
    assert after_reload.json()["requirements"][1]["id"] == requirement_ids[0]


def test_omission_null_and_failed_budget_update_preserve_state(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client).json()

    omitted = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "notes": "Keep this vacuum lightweight"},
    )
    assert omitted.status_code == 200
    assert omitted.json()["budget_maximum"] == "400.00"
    assert omitted.json()["notes"] == "Keep this vacuum lightweight"

    invalid = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 2, "budget_target": "500.00"},
    )
    _error(invalid, 422, "invalid_request")
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 2
    assert current["budget_maximum"] == "400.00"
    assert current["budget_target"] is None

    cleared = client.patch(
        f"/projects/{project['id']}",
        json={
            "expected_version": 2,
            "budget_target": None,
            "budget_maximum": None,
            "budget_currency": None,
            "category": None,
        },
    )
    assert cleared.status_code == 200
    assert cleared.json()["budget_maximum"] is None
    assert cleared.json()["budget_currency"] is None


def test_revision_conflicts_prevent_project_and_requirement_partial_writes(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client).json()
    requirement_id = project["requirements"][0]["id"]

    first = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "title": "Updated vacuum project"},
    )
    assert first.status_code == 200
    stale_project = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "goal": "This must not be applied"},
    )
    error = _error(stale_project, 409, "revision_conflict")
    assert error["details"]["current_version"] == 2
    stale_requirement = client.patch(
        f"/projects/{project['id']}/requirements/{requirement_id}",
        json={"expected_version": 1, "label": "Stale label"},
    )
    _error(stale_requirement, 409, "revision_conflict")

    current = client.get(f"/projects/{project['id']}").json()
    assert current["title"] == "Updated vacuum project"
    assert current["goal"] == "Find a pet-hair vacuum"
    assert current["requirements"][0]["label"] == "Works well on pet hair"
    assert current["revision"] == 2


@pytest.mark.parametrize(
    ("method", "target_kind"),
    [("patch", "missing"), ("patch", "foreign"), ("delete", "missing"), ("delete", "foreign")],
)
def test_missing_or_foreign_requirement_precedes_stale_revision_conflict(
    project_api, method, target_kind
):
    client, _owner, _engine = project_api
    project = _create_project(client).json()
    client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "title": "Changed project"},
    )
    if target_kind == "missing":
        requirement_id = str(uuid4())
    else:
        foreign_project = _create_project(client, title="Another project").json()
        requirement_id = foreign_project["requirements"][0]["id"]

    path = f"/projects/{project['id']}/requirements/{requirement_id}"
    if method == "patch":
        response = client.patch(path, json={"expected_version": 1, "label": "Stale label"})
    else:
        response = client.delete(path, params={"expected_version": 1})
    _error(response, 404, "not_found")


def test_different_owner_gets_not_found_for_project_and_nested_requirement(project_api):
    client, owner, _engine = project_api
    project = _create_project(client).json()
    requirement_id = project["requirements"][0]["id"]
    owner["id"] = uuid4()

    _error(client.get(f"/projects/{project['id']}"), 404, "not_found")
    _error(
        client.delete(
            f"/projects/{project['id']}/requirements/{requirement_id}?expected_version=1"
        ),
        404,
        "not_found",
    )
    _error(
        client.patch(
            f"/projects/{project['id']}",
            json={"expected_version": 1, "title": "Foreign edit"},
        ),
        404,
        "not_found",
    )
    assert client.get("/projects").json()["items"] == []


def test_archive_restore_and_tombstone_lifecycle(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client).json()

    archived = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "status": "archived"},
    ).json()
    assert archived["status"] == "archived"
    restored = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 2, "status": "active"},
    ).json()
    assert restored["status"] == "active"

    deleted = client.delete(f"/projects/{project['id']}?expected_version={restored['revision']}")
    assert deleted.status_code == 204
    assert all(item["id"] != project["id"] for item in client.get("/projects").json()["items"])
    _error(client.get(f"/projects/{project['id']}/requirements"), 404, "not_found")
    _error(client.get(f"/projects/{project['id']}"), 404, "not_found")


def test_unknown_fields_missing_resources_and_schema_errors_use_error_envelope(project_api):
    client, _owner, _engine = project_api
    unknown = client.post(
        "/projects",
        json={"title": "Vacuum", "goal": "Find one", "owner_id": "client-controlled"},
    )
    _error(unknown, 422, "validation_error")
    invalid_currency = client.post(
        "/projects",
        json={"title": "Vacuum", "goal": "Find one", "budget_currency": "ZZZ"},
    )
    _error(invalid_currency, 422, "validation_error")
    project = client.post("/projects", json={"title": "Vacuum", "goal": "Find one"}).json()
    invalid_operator = client.post(
        f"/projects/{project['id']}/requirements",
        params={"expected_version": 1},
        json={
            "kind": "must_have",
            "label": "Light weight",
            "attribute_key": "weight",
            "operator": "gte",
            "value": "light",
        },
    )
    _error(invalid_operator, 422, "validation_error")
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 1

    missing = client.get("/projects/00000000-0000-0000-0000-000000000001")
    _error(missing, 404, "not_found")


def test_pagination_has_opaque_deterministic_tie_breaker(project_api):
    client, _owner, engine = project_api
    ids = []
    for title in ("One", "Two", "Three"):
        response = client.post("/projects", json={"title": title, "goal": f"Find {title}"})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE shopping_projects SET updated_at = '2026-10-03T12:00:00+00:00'")
        )

    first = client.get("/projects?limit=2")
    assert first.status_code == 200
    page_one = first.json()
    assert page_one["next_cursor"]
    assert page_one["next_cursor"] != ids[0]
    second = client.get("/projects", params={"limit": 2, "cursor": page_one["next_cursor"]})
    assert second.status_code == 200
    assert [item["id"] for item in page_one["items"] + second.json()["items"]] == sorted(ids)
    _error(client.get("/projects?cursor=not-a-valid-cursor"), 422, "invalid_request")


def test_two_stale_tabs_cannot_both_commit(project_api):
    client, _owner, _engine = project_api
    project = _create_project(client).json()
    barrier = Barrier(2)

    def update(notes: str):
        barrier.wait()
        return client.patch(
            f"/projects/{project['id']}",
            json={"expected_version": 1, "notes": notes},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(update, ["First tab", "Second tab"]))
    assert sorted(response.status_code for response in responses) == [200, 409]
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 2
    assert current["notes"] in {"First tab", "Second tab"}
