from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.conversations.task import build_request
from shopping.projects.models import ProjectProductDecision, ShoppingProject
from shopping.projects.schemas import ProjectRead
from shopping.research.commands import _snapshot
from shopping.research.schemas import ResearchCreate

pytestmark = pytest.mark.db


def create_project(client, title: str, category: str = "furniture"):
    response = client.post(
        "/projects",
        json={
            "title": title,
            "goal": f"Find {title.lower()}",
            "category": category,
            "requirements": [
                {
                    "kind": "preference",
                    "label": "Prefers compact furniture",
                    "detail": None,
                    "attribute_key": None,
                    "operator": None,
                    "value": None,
                    "unit": None,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def candidate_command(project, profile_version: int = 1) -> dict:
    return {
        "expected_project_version": project["revision"],
        "expected_profile_version": profile_version,
        "source_requirement_id": project["requirements"][0]["id"],
        "label": "Prefers compact furniture",
        "key": "statement",
        "operator": None,
        "value": "prefers compact furniture",
        "unit": "",
        "category_scopes": ["furniture"],
        "rationale": "The user selected this for broader reuse.",
    }


def test_explicit_candidate_promotion_reuse_edit_and_revoke(project_api) -> None:
    client, _owner, _engine = project_api
    source = create_project(client, "Compact sofa")
    profile = client.get("/profile").json()
    assert profile["revision"] == 1

    command = candidate_command(source, profile["revision"])
    created = client.post(f"/projects/{source['id']}/preference-candidates", json=command)
    assert created.status_code == 201, created.text
    candidate = created.json()["candidate"]
    assert candidate["status"] == "pending"
    assert candidate["source_project_revision"] == source["revision"]

    duplicate = client.post(f"/projects/{source['id']}/preference-candidates", json=command)
    assert duplicate.status_code == 201
    assert duplicate.json()["replayed"] is True
    assert duplicate.json()["candidate"]["id"] == candidate["id"]

    profile = client.get("/profile").json()
    promoted = client.post(
        f"/profile/preference-candidates/{candidate['id']}/accept",
        json={"expected_profile_version": profile["revision"]},
    )
    assert promoted.status_code == 200, promoted.text
    preference = promoted.json()["preference"]
    assert preference["strength"] == "soft"
    assert preference["category_scopes"] == ["furniture"]
    assert preference["source_project_id"] == source["id"]

    replay = client.post(
        f"/profile/preference-candidates/{candidate['id']}/accept",
        json={"expected_profile_version": profile["revision"]},
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True

    destination = create_project(client, "Desk chair")
    updated = client.patch(
        f"/projects/{destination['id']}",
        json={"expected_version": destination["revision"], "reuse_preferences": True},
    ).json()
    suggestions = client.get(f"/projects/{destination['id']}/preference-suggestions").json()
    assert [item["id"] for item in suggestions["items"]] == [preference["id"]]

    applied = client.post(
        f"/projects/{destination['id']}/preferences/{preference['id']}/apply",
        params={"expected_project_version": updated["revision"]},
    )
    assert applied.status_code == 200, applied.text
    applied_requirement = applied.json()["requirements"][-1]
    assert applied_requirement["source_preference_id"] == preference["id"]
    assert applied_requirement["source_preference_revision"] == preference["revision"]
    assert applied_requirement["source_preference_scope"] == ["furniture"]

    project_read = ProjectRead.model_validate(applied.json())
    conversation_context = build_request(project_read, "Compare the options", []).input["context"]
    conversation_origin = conversation_context["requirements"][-1]["preference_origin"]
    assert conversation_origin == {
        "preference_id": preference["id"],
        "preference_revision": preference["revision"],
        "scope": ["furniture"],
    }
    with Session(_engine) as session:
        stored_project = session.get(ShoppingProject, project_read.id)
        research_context = _snapshot(
            session,
            stored_project,
            ResearchCreate(
                objective="Research furniture options",
                request_key="preference-snapshot-1",
                expected_version=project_read.revision,
            ),
        )
    assert research_context["requirements"][-1]["preference_origin"] == conversation_origin

    profile = client.get("/profile").json()
    edited = client.patch(
        f"/profile/preferences/{preference['id']}",
        json={
            "expected_profile_version": profile["revision"],
            "expected_preference_revision": preference["revision"],
            "label": "Prefers smaller furniture",
        },
    )
    assert edited.status_code == 200, edited.text
    edited_preference = next(
        item for item in edited.json()["preferences"] if item["id"] == preference["id"]
    )
    assert edited_preference["revision"] == preference["revision"] + 1

    revoked = client.delete(
        f"/profile/preferences/{preference['id']}",
        params={"expected_profile_version": edited.json()["revision"]},
    )
    assert revoked.status_code == 200, revoked.text
    revoked_preference = next(
        item for item in revoked.json()["preferences"] if item["id"] == preference["id"]
    )
    assert revoked_preference["status"] == "revoked"

    new_project = create_project(client, "Storage bench")
    client.patch(
        f"/projects/{new_project['id']}",
        json={"expected_version": new_project["revision"], "reuse_preferences": True},
    )
    assert client.get(f"/projects/{new_project['id']}/preference-suggestions").json()["items"] == []


def test_stale_and_foreign_owner_candidates_are_not_promoted(project_api) -> None:
    client, current_owner, _engine = project_api
    project = create_project(client, "Entryway bench")
    profile = client.get("/profile").json()
    pending = client.post(
        f"/projects/{project['id']}/preference-candidates",
        json=candidate_command(project, profile["revision"]),
    ).json()["candidate"]

    changed = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": project["revision"], "title": "Small entryway bench"},
    )
    assert changed.status_code == 200
    stale = client.post(
        f"/profile/preference-candidates/{pending['id']}/accept",
        json={"expected_profile_version": profile["revision"] + 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "candidate_stale"

    current_owner["id"] = uuid4()
    assert client.get("/profile").json()["preferences"] == []
    foreign = client.post(
        f"/profile/preference-candidates/{pending['id']}/accept",
        json={"expected_profile_version": 1},
    )
    assert foreign.status_code == 404


def test_rejected_product_judgment_requires_explicit_profile_review(project_api) -> None:
    client, current_owner, engine = project_api
    project = create_project(client, "Previously owned desk", category="office")
    with Session(engine) as session:
        product = Product(
            owner_id=current_owner["id"],
            canonical_name="Compact writing desk",
            category="office",
        )
        session.add(product)
        session.flush()
        variant = ProductVariant(
            product_id=product.id,
            display_name="Walnut",
            identity_key="finish=walnut",
            identity_attributes={},
            category_attributes={},
        )
        session.add(variant)
        session.flush()
        project_product = ProjectProduct(
            project_id=project["id"], variant_id=variant.id, discovery_reason="local test"
        )
        session.add(project_product)
        session.flush()
        decision = ProjectProductDecision(
            owner_id=current_owner["id"],
            project_id=project["id"],
            project_product_id=project_product.id,
            state="rejected",
            rejection_reason="already_owned",
            reason="We already own this exact item.",
            concerns=[],
            actor="owner",
            origin="command",
            version=1,
        )
        session.add(decision)
        session.commit()
        project_product_id = project_product.id
        decision_id = decision.id

    profile = client.get("/profile").json()
    candidate_response = client.post(
        f"/projects/{project['id']}/preference-candidates",
        json={
            "expected_project_version": project["revision"],
            "expected_profile_version": profile["revision"],
            "source_project_product_id": str(project_product_id),
            "label": "Avoid compact writing desks already owned",
            "key": "statement",
            "operator": None,
            "value": "avoid this kind of item when we already own one",
            "unit": "",
            "category_scopes": ["office"],
            "rationale": "Explicitly selected from an already-owned rejection.",
        },
    )
    assert candidate_response.status_code == 201, candidate_response.text
    candidate = candidate_response.json()["candidate"]
    assert candidate["source_kind"] == "decision"
    assert candidate["source_project_product_id"] == str(project_product_id)
    assert candidate["source_decision_id"] == str(decision_id)
    assert candidate["status"] == "pending"
    assert client.get("/profile").json()["preferences"] == []

    reviewed = client.post(
        f"/profile/preference-candidates/{candidate['id']}/accept",
        json={"expected_profile_version": profile["revision"] + 1},
    )
    assert reviewed.status_code == 200, reviewed.text
    preference = reviewed.json()["preference"]
    assert preference["source_kind"] == "decision"
    assert preference["source_decision_id"] == str(decision_id)
    assert preference["source_available"] is True
