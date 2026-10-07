import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shopping.conversations.task import SYSTEM_INSTRUCTIONS, build_request
from shopping.preferences.schemas import (
    CandidateCreate,
    preference_is_suggestible,
    promotable_requirement_kind,
)
from shopping.projects.schemas import ProjectRead
from shopping.research.product_task import SYSTEM_INSTRUCTIONS as PRODUCT_RESEARCH_INSTRUCTIONS
from shopping.research.task import SYSTEM_INSTRUCTIONS as DISCOVERY_INSTRUCTIONS

FIXTURES = Path(__file__).with_name("scenarios.json")
SCENARIOS = json.loads(FIXTURES.read_text())


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[item["name"] for item in SCENARIOS])
def test_preference_boundary_scenarios(scenario: dict) -> None:
    if "requirement_kind" in scenario:
        assert promotable_requirement_kind(scenario["requirement_kind"]) is scenario.get(
            "promotable", False
        )

    if "scopes" in scenario and (
        scenario["source_kind"] == "decision" or scenario.get("promotable", False)
    ):
        suggestible = preference_is_suggestible(
            scenario["status"],
            scenario["scopes"],
            scenario["category"],
            profile_reuse_enabled=True,
            project_reuse_enabled=True,
        )
        assert suggestible is scenario["suggestible"]

    if scenario.get("key") == "max_budget":
        command = {
            "expected_project_version": 1,
            "expected_profile_version": 1,
            "source_requirement_id": str(uuid4()),
            "label": scenario["label"],
            "key": scenario["key"],
            "operator": scenario["operator"],
            "value": scenario["value"],
            "unit": scenario["unit"],
            "category_scopes": ["furniture"],
        }
        CandidateCreate.model_validate(command)

    if scenario.get("explicit_candidate_required"):
        with pytest.raises(ValidationError, match="exactly one"):
            CandidateCreate.model_validate(
                {
                    "expected_project_version": 1,
                    "expected_profile_version": 1,
                    "label": "Avoid this rejected item",
                    "key": "statement",
                    "value": "avoid this rejected item",
                    "category_scopes": scenario["scopes"],
                }
            )


def test_soft_profile_conflict_keeps_hard_project_requirement_in_assistant_context() -> None:
    project_id = uuid4()
    now = "2026-10-05T12:00:00Z"
    project = ProjectRead.model_validate(
        {
            "id": str(project_id),
            "title": "Desk for a low alcove",
            "goal": "Find a desk that fits beneath the alcove",
            "category": "office",
            "status": "active",
            "budget_target": None,
            "budget_maximum": None,
            "budget_currency": None,
            "notes": None,
            "reuse_preferences": True,
            "revision": 4,
            "created_at": now,
            "updated_at": now,
            "requirements": [
                {
                    "id": str(uuid4()),
                    "project_id": str(project_id),
                    "kind": "constraint",
                    "label": "Must fit under 27 inches",
                    "detail": None,
                    "attribute_key": "max_height",
                    "operator": "lte",
                    "value": 27,
                    "unit": "in",
                    "position": 0,
                    "origin": "user",
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": str(uuid4()),
                    "project_id": str(project_id),
                    "kind": "preference",
                    "label": "Prefers a taller desk",
                    "detail": None,
                    "attribute_key": "min_height",
                    "operator": "gte",
                    "value": 30,
                    "unit": "in",
                    "position": 1,
                    "origin": "user",
                    "source_preference_id": str(uuid4()),
                    "source_preference_revision": 2,
                    "source_preference_scope": ["office"],
                    "created_at": now,
                    "updated_at": now,
                },
                {
                    "id": str(uuid4()),
                    "project_id": str(project_id),
                    "kind": "constraint",
                    "label": "Keep the desk below the shelf",
                    "detail": None,
                    "attribute_key": "max_height",
                    "operator": "lte",
                    "value": 25,
                    "unit": "in",
                    "position": 2,
                    "origin": "user",
                    "source_preference_id": str(uuid4()),
                    "source_preference_revision": 3,
                    "source_preference_scope": ["office"],
                    "created_at": now,
                    "updated_at": now,
                },
            ],
        }
    )

    context = build_request(project, "Find a suitable desk", []).input["context"]
    requirements = context["requirements"]
    assert [item["kind"] for item in requirements] == [
        "constraint",
        "preference",
        "constraint",
    ]
    assert requirements[0]["label"] == "Must fit under 27 inches"
    assert requirements[1]["preference_origin"]["scope"] == ["office"]
    assert requirements[2]["preference_origin"]["preference_revision"] == 3
    assert (
        "current explicit project requirement kind determines authority"
        in SYSTEM_INSTRUCTIONS.lower()
    )
    assert "profile-origin copy the user explicitly hardened" in SYSTEM_INSTRUCTIONS.lower()
    assert "provenance never overrides that current kind" in SYSTEM_INSTRUCTIONS.lower()
    for instructions in (DISCOVERY_INSTRUCTIONS, PRODUCT_RESEARCH_INSTRUCTIONS):
        assert (
            "current explicit project requirement kind determines authority" in instructions.lower()
        )
        assert "profile-origin copy the user explicitly hardened" in instructions.lower()
        assert "provenance never overrides current kind" in instructions.lower()
