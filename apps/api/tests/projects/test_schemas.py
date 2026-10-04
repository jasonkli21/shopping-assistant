from decimal import Decimal

import pytest
from pydantic import ValidationError

from shopping.projects.schemas import ProjectCreate, ProjectPatch, RequirementCreate


def test_vacuum_budget_and_text_or_structured_requirements_are_valid():
    project = ProjectCreate(
        title=" Vacuum for apartment ",
        goal=" Find a vacuum for pet hair ",
        budget_maximum="400.00",
        budget_currency="usd",
        requirements=[
            {"kind": "must_have", "label": "Works well for pet hair"},
            {
                "kind": "preference",
                "label": "Removable battery",
                "attribute_key": "battery_removable",
                "operator": "eq",
                "value": True,
            },
        ],
    )
    assert project.title == "Vacuum for apartment"
    assert project.budget_maximum == Decimal("400.00")
    assert project.budget_currency == "USD"
    assert project.requirements[0].value is None


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "Vacuum", "goal": "Find one", "budget_maximum": "400"},
        {
            "title": "Vacuum",
            "goal": "Find one",
            "budget_target": "401",
            "budget_maximum": "400",
            "budget_currency": "USD",
        },
        {"title": "Vacuum", "goal": "Find one", "budget_currency": "ZZZ"},
        {"title": "Vacuum", "goal": "Find one", "budget_maximum": 400, "budget_currency": "USD"},
        {"title": "Vacuum", "goal": "Find one", "owner_id": "00000000-0000-0000-0000-000000000001"},
        {"title": "Vacuum", "goal": "Find one", "unexpected": True},
    ],
)
def test_project_create_rejects_invalid_budget_or_unknown_fields(payload):
    with pytest.raises(ValidationError):
        ProjectCreate.model_validate(payload)


@pytest.mark.parametrize(
    "criterion",
    [
        {"attribute_key": "weight", "operator": "gte", "value": "light"},
        {"attribute_key": "features", "operator": "contains", "value": ["pet hair"]},
        {"attribute_key": "voltage", "operator": "one_of", "value": []},
        {"attribute_key": "weight", "operator": "gte", "value": float("inf")},
    ],
)
def test_typed_requirement_rejects_invalid_operator_value_shapes(criterion):
    with pytest.raises(ValidationError):
        RequirementCreate(kind="must_have", label="A requirement", **criterion)


def test_project_patch_keeps_unset_distinct_from_explicit_null():
    omitted = ProjectPatch(expected_version=1, notes="New notes")
    cleared = ProjectPatch(expected_version=1, notes=None, category=None)
    assert omitted.model_fields_set == {"expected_version", "notes"}
    assert cleared.model_fields_set == {"expected_version", "notes", "category"}
