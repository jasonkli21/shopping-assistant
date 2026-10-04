import asyncio
import json
from pathlib import Path

import pytest

from shopping.conversations.task import validate_output
from shopping.integrations.personal_ai.client import AIRequest
from shopping.integrations.personal_ai.fake import FakePersonalAIClient

FIXTURES = Path(__file__).parent
CASES = [json.loads(path.read_text()) for path in sorted(FIXTURES.glob("*.json"))]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_offline_intent_fixture_structural_acceptance(case):
    request = AIRequest(
        task="interpret_shopping_intent.v1",
        input={
            "context": {
                "new_user_message": case["message"],
                "requirements": [],
                "project": {
                    "budget_target": None,
                    "budget_maximum": None,
                    "budget_currency": None,
                },
            }
        },
    )
    response = asyncio.run(FakePersonalAIClient().generate(request))
    output = validate_output(response.output, request.input["context"])
    question_text = " ".join(output.clarification_questions).lower()
    operation_kinds = {
        item.fields.kind if item.operation == "add" else item.operation
        for item in output.requirement_operations
    }

    assert not case.get("expected_question") or case["expected_question"] in question_text
    assert output.project_updates.category == case.get("expected_category")
    assert not case.get("expected_operation") or case["expected_operation"] in operation_kinds
    assert not case.get("expected_no_mutation") or output.mutation_payload() is None
    if case.get("forbid_budget_currency"):
        assert output.project_updates.budget_currency is None
        assert output.project_updates.budget_maximum is None
    if case.get("expected_unit"):
        added = next(item for item in output.requirement_operations if item.operation == "add")
        assert added.fields.unit == case["expected_unit"]


def test_output_schema_rejects_malformed_budget_and_unknown_fields():
    with pytest.raises(ValueError, match="did not match"):
        validate_output(
            {
                "assistant_message": "I understood the amount.",
                "clarification_questions": [],
                "project_updates": {"budget_maximum": "400"},
                "requirement_operations": [],
            }
        )


def test_output_schema_rejects_oversized_structured_responses():
    from shopping.conversations.task import MAX_OUTPUT_CHARS

    with pytest.raises(ValueError, match="size limit"):
        validate_output({"assistant_message": "x" * (MAX_OUTPUT_CHARS + 1)})


def test_budget_updates_cannot_clear_category_or_relabel_an_existing_amount():
    with pytest.raises(ValueError, match="did not match"):
        validate_output(
            {
                "assistant_message": "I updated the category.",
                "clarification_questions": [],
                "project_updates": {"category": " "},
                "requirement_operations": [],
            }
        )
    with pytest.raises(ValueError, match="relabel an existing budget"):
        validate_output(
            {
                "assistant_message": "I changed the currency.",
                "clarification_questions": [],
                "project_updates": {"budget_currency": "CAD"},
                "requirement_operations": [],
            },
            {
                "project": {
                    "budget_target": None,
                    "budget_maximum": "400.00",
                    "budget_currency": "USD",
                },
                "requirements": [],
            },
        )
    with pytest.raises(ValueError, match="did not match"):
        validate_output(
            {
                "assistant_message": "Here is a change.",
                "clarification_questions": [],
                "project_updates": {},
                "requirement_operations": [],
                "tool_call": {"url": "https://example.invalid"},
            }
        )


def test_output_schema_rejects_foreign_existing_requirement_id():
    with pytest.raises(ValueError, match="unavailable requirement"):
        validate_output(
            {
                "assistant_message": "I found a requirement to update.",
                "clarification_questions": [],
                "project_updates": {},
                "requirement_operations": [
                    {
                        "operation": "remove",
                        "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
                    }
                ],
            },
            {
                "project": {"budget_target": None, "budget_maximum": None, "budget_currency": None},
                "requirements": [],
            },
        )


def test_prompt_context_is_bounded_without_truncating_the_current_message():
    from datetime import UTC, datetime
    from uuid import uuid4

    from shopping.conversations.task import MAX_CONTEXT_CHARS, build_request
    from shopping.projects.schemas import ProjectRead

    now = datetime.now(UTC)
    project = ProjectRead.model_validate(
        {
            "id": str(uuid4()),
            "title": "Desk",
            "goal": "Find a desk",
            "category": None,
            "status": "active",
            "budget_target": None,
            "budget_maximum": None,
            "budget_currency": None,
            "notes": None,
            "revision": 1,
            "created_at": now,
            "updated_at": now,
            "requirements": [],
        }
    )
    request = build_request(project, "A" * 4000, [{"role": "user", "text": "old" * 2000}])
    context = request.input["context"]
    assert len(json.dumps(context, ensure_ascii=False, separators=(",", ":"))) <= MAX_CONTEXT_CHARS
    assert context["new_user_message"] == "A" * 4000
