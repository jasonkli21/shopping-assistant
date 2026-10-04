from __future__ import annotations

import json
from pathlib import Path

import pytest

from shopping.integrations.personal_ai.client import AIRequest
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.research.task import TASK_NAME, validate_output

FIXTURE_DIR = Path(__file__).parent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fixture_path", sorted(FIXTURE_DIR.glob("*.json")), ids=lambda path: path.stem
)
async def test_discovery_planner_fixtures_preserve_constraints_and_clarify_ambiguity(fixture_path):
    fixture = json.loads(fixture_path.read_text())
    context = {
        "objective": fixture["objective"],
        "project": fixture["project"],
        "requirements": fixture["requirements"],
    }
    client = FakePersonalAIClient()
    response = await client.generate(
        AIRequest(
            task=TASK_NAME,
            input={"context": context, "response_schema": {}},
        )
    )
    plan = validate_output(response.output, context, max_queries=8)
    if fixture.get("expected_clarification"):
        assert plan.clarification
        assert not plan.queries
    else:
        assert plan.queries
        text = " ".join(item.text.casefold() for item in plan.queries)
        assert all(term.casefold() in text for term in fixture["expected_terms"])


@pytest.mark.parametrize(
    ("query", "message"),
    [
        ("works well on pet hair under $400 USD", "project category"),
        ("vacuum works well on pet hair below $399 USD", "exact project budget"),
        ("vacuum works well on pet hair below 400 CAD", "exact project budget"),
        ("Vacuum under $400 USD", "required shopping constraint"),
        ("Vacuum pet hair under $400 USD", "required shopping constraint"),
    ],
)
def test_discovery_plan_rejects_omitted_category_constraint_or_exact_budget(query, message):
    snapshot = {
        "objective": "Vacuum for pet hair",
        "project": {
            "category": "Vacuum",
            "budget_maximum": "400.00",
            "budget_currency": "USD",
        },
        "requirements": [{"kind": "must_have", "label": "Works well on pet hair"}],
    }
    output = {"queries": [{"text": query, "purpose": "Find candidates"}]}

    with pytest.raises(ValueError, match=message):
        validate_output(output, snapshot, max_queries=8)


def test_discovery_plan_accepts_exact_decimal_budget_with_currency_code():
    snapshot = {
        "project": {
            "category": "Vacuum",
            "budget_maximum": "400.00",
            "budget_currency": "USD",
        },
        "requirements": [],
    }

    plan = validate_output(
        {"queries": [{"text": "Vacuum up to 400.00 USD", "purpose": "Find options"}]},
        snapshot,
        max_queries=8,
    )

    assert plan.queries[0].text == "Vacuum up to 400.00 USD"
