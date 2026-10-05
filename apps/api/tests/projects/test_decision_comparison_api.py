from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
from shopping.projects.models import DecisionEvent, ProjectProductDecision

pytestmark = pytest.mark.db


def _project(client):
    response = client.post(
        "/projects",
        json={"title": "Apartment vacuum", "goal": "Compare quiet pet-hair vacuums"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _add_variants(engine, owner_id, project_id):
    ids = []
    with Session(engine) as session:
        for index, (width, unit) in enumerate(((2.54, "cm"), (25.4, "mm")), start=1):
            product_id, variant_id, project_product_id = uuid4(), uuid4(), uuid4()
            product = Product(
                id=product_id,
                owner_id=owner_id,
                canonical_name=f"Vacuum {index}",
                brand="Example",
                category="vacuum",
                revision=1,
            )
            variant = ProductVariant(
                id=variant_id,
                product_id=product_id,
                display_name=f"Model {index}, US",
                identity_key=f"model:{index}|region:us",
                identity_attributes={"region": {"value": "US"}},
                category_attributes={
                    "clearance": {"value": width, "unit": unit},
                    "tank_capacity": {
                        "value": 12,
                        "unit": "L" if index == 1 else "gal",
                    },
                },
                revision=1,
            )
            session.add(product)
            session.flush()
            session.add(variant)
            session.flush()
            session.add(
                ProjectProduct(
                    id=project_product_id,
                    project_id=project_id,
                    variant_id=variant_id,
                    discovery_reason="Added by a deterministic decision fixture",
                )
            )
            ids.append((product_id, variant_id, project_product_id))
        session.commit()
    return ids


def _decision_body(version, key, **updates):
    return {
        "expected_version": version,
        "request_key": key,
        "reason": "Fits the saved requirements",
        "concerns": [],
        **updates,
    }


def test_decisions_notes_favorites_and_idempotent_replay_are_separate(project_api):
    client, owner, engine = project_api
    project = _project(client)
    (_product_id, variant_id, project_product_id), _ = _add_variants(
        engine, owner["id"], project["id"]
    )
    decision_path = f"/projects/{project['id']}/shortlist/{project_product_id}"

    shortlist = _decision_body(1, "decision-shortlist-0001")
    first = client.post(decision_path, json=shortlist)
    assert first.status_code == 200, first.text
    assert first.json()["event"]["to_state"] == "shortlisted"
    replay = client.post(decision_path, json=shortlist)
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 2

    rejection = client.post(
        f"/projects/{project['id']}/rejections/{project_product_id}",
        json=_decision_body(2, "decision-reject-00001", rejection_reason="too_large"),
    )
    assert rejection.status_code == 200, rejection.text
    assert client.get(f"/projects/{project['id']}/shortlist").json()["items"] == []
    assert (
        client.get(f"/projects/{project['id']}/rejections").json()["items"][0]["decision"]["state"]
        == "rejected"
    )

    undo = client.delete(
        f"/projects/{project['id']}/rejections/{project_product_id}",
        json=_decision_body(3, "decision-undo-reject-0001"),
    )
    assert undo.status_code == 200, undo.text
    purchase = client.post(
        f"/projects/{project['id']}/products/{project_product_id}/purchased",
        json=_decision_body(4, "decision-purchase-00001"),
    )
    assert purchase.status_code == 200, purchase.text
    blocked_transition = client.post(
        decision_path,
        json=_decision_body(5, "decision-shortlist-0002"),
    )
    assert blocked_transition.status_code == 409
    current = client.get(f"/projects/{project['id']}/products/{project_product_id}/decision").json()
    assert current["state"] == "purchased"
    assert len(current["events"]) == 4

    note_path = f"/projects/{project['id']}/products/{project_product_id}/notes"
    note = client.put(note_path, json={"expected_version": 5, "text": "Fits the hallway closet."})
    assert note.status_code == 200, note.text
    assert note.json()["note"]["text"] == "Fits the hallway closet."
    updated_note = client.put(
        note_path,
        json={"expected_version": 6, "text": "Fits the hallway closet; replaceable filter."},
    )
    assert updated_note.status_code == 200, updated_note.text
    assert updated_note.json()["note"]["version"] == 2
    assert client.get(note_path).json()["text"].endswith("replaceable filter.")

    favorite = client.put(f"/saved-products/{variant_id}/favorite", json={"expected_version": 0})
    assert favorite.status_code == 200, favorite.text
    assert favorite.json()["favorite"] is True
    project_revision = client.get(f"/projects/{project['id']}").json()["revision"]
    assert project_revision == 7
    assert client.get("/saved-products").json()["items"][0]["variant_id"] == str(variant_id)
    unfavorite = client.delete(
        f"/saved-products/{variant_id}/favorite", json={"expected_version": 1}
    )
    assert unfavorite.status_code == 200, unfavorite.text
    assert unfavorite.json()["favorite"] is False
    with Session(engine) as session:
        assert (
            session.scalar(
                select(ProjectProductDecision.state).where(
                    ProjectProductDecision.project_product_id == project_product_id
                )
            )
            == "purchased"
        )
        assert (
            len(
                session.scalars(
                    select(DecisionEvent).where(
                        DecisionEvent.project_product_id == project_product_id
                    )
                ).all()
            )
            == 4
        )


def test_decision_rejects_an_offer_from_a_different_variant(project_api):
    client, owner, engine = project_api
    project = _project(client)
    first, second = _add_variants(engine, owner["id"], project["id"])
    offer_id = uuid4()
    with Session(engine) as session:
        session.add(
            RetailOffer(
                id=offer_id,
                owner_id=owner["id"],
                variant_id=second[1],
                idempotency_key="foreign-decision-offer",
                retailer_name="Example retailer",
                url="https://shop.example/vacuum",
                amount=Decimal("129.00"),
                currency="USD",
                availability="in_stock",
                condition="new",
                observed_at=datetime.now(UTC),
            )
        )
        session.commit()

    response = client.post(
        f"/projects/{project['id']}/shortlist/{first[2]}",
        json=_decision_body(1, "decision-wrong-offer-0001", selected_offer_id=str(offer_id)),
    )
    assert response.status_code == 404
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 1
    state = client.get(f"/projects/{project['id']}/products/{first[2]}/decision").json()
    assert state["state"] == "considering"


def test_comparison_snapshots_normalize_units_and_keep_unknown_differences(project_api):
    client, owner, engine = project_api
    project = _project(client)
    (_one_product, _one_variant, one), (_two_product, _two_variant, two) = _add_variants(
        engine, owner["id"], project["id"]
    )
    base_path = f"/projects/{project['id']}/comparisons"
    created = client.post(
        base_path,
        json={
            "expected_version": 1,
            "title": "Vacuum clearances",
            "project_product_ids": [str(one), str(two)],
            "dimensions": [
                {"key": "clearance", "label": "Clearance", "dimension_type": "fact"},
                {"key": "tank_capacity", "label": "Tank capacity", "dimension_type": "fact"},
                {"key": "warranty", "label": "Warranty", "dimension_type": "evidence"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    first_snapshot = created.json()
    assert first_snapshot["stale"] is False
    assert all(item["product_revision"] == 1 for item in first_snapshot["products"])
    assert all(item["variant_revision"] == 1 for item in first_snapshot["products"])
    clearance = first_snapshot["dimensions"][0]
    assert clearance["equal"] is True
    assert clearance["cells"][0]["comparison_value"] == clearance["cells"][1]["comparison_value"]
    tank_capacity = first_snapshot["dimensions"][1]
    assert tank_capacity["equal"] is False
    assert all(cell["status"] == "known" for cell in tank_capacity["cells"])
    assert all(cell["status"] == "unknown" for cell in first_snapshot["dimensions"][2]["cells"])

    comparison_id = first_snapshot["id"]
    differences = client.patch(
        f"{base_path}/{comparison_id}",
        json={
            "expected_version": 2,
            "expected_comparison_version": 1,
            "display_mode": "differences",
        },
    )
    assert differences.status_code == 200, differences.text
    difference_view = differences.json()
    assert difference_view["snapshot_id"] != first_snapshot["snapshot_id"]
    assert difference_view["hidden_equal_dimensions"] == 1
    assert [item["key"] for item in difference_view["dimensions"]] == [
        "tank_capacity",
        "warranty",
    ]
    assert [cell["status"] for cell in difference_view["dimensions"][0]["cells"]] == [
        "unknown",
        "unknown",
    ]

    with Session(engine) as session:
        variant = session.get(ProductVariant, _two_variant)
        assert variant is not None
        variant.category_attributes = {"clearance": {"value": 50, "unit": "mm"}}
        session.commit()
    stale = client.get(f"{base_path}/{comparison_id}")
    assert stale.status_code == 200
    assert stale.json()["stale"] is True

    regenerated = client.post(
        f"{base_path}/{comparison_id}/regenerate",
        json={"expected_version": 3, "expected_comparison_version": 2},
    )
    assert regenerated.status_code == 200, regenerated.text
    assert regenerated.json()["snapshot_id"] != difference_view["snapshot_id"]
    assert regenerated.json()["comparison_revision"] == 3
    assert regenerated.json()["stale"] is False
