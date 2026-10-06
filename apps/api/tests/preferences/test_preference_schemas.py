from uuid import uuid4

import pytest
from pydantic import ValidationError

from shopping.preferences.schemas import CandidateCreate, PreferencePatch


def candidate_payload(**overrides) -> dict:
    return {
        "expected_project_version": 1,
        "expected_profile_version": 1,
        "source_requirement_id": str(uuid4()),
        "label": "Prefers compact furniture",
        "key": "statement",
        "operator": None,
        "value": "prefers compact furniture",
        "unit": "",
        "category_scopes": ["Furniture"],
        "rationale": "Explicitly selected from a project preference.",
        **overrides,
    }


def test_candidate_normalizes_explicit_category_scope_and_key() -> None:
    candidate = CandidateCreate.model_validate(
        candidate_payload(key="Room_Size", operator="eq", value=4)
    )

    assert candidate.key == "room_size"
    assert candidate.category_scopes == ["furniture"]


def test_money_preferences_require_category_and_currency() -> None:
    with pytest.raises(ValidationError, match="category-specific"):
        CandidateCreate.model_validate(
            candidate_payload(
                label="Keep the budget under $500",
                key="max_budget",
                operator="lte",
                value="500.00",
                unit="USD",
                category_scopes=["*"],
            )
        )

    with pytest.raises(ValidationError, match="currency"):
        CandidateCreate.model_validate(
            candidate_payload(
                label="Keep the budget under $500",
                key="max_budget",
                operator="lte",
                value="500.00",
                unit="",
                category_scopes=["furniture"],
            )
        )

    with pytest.raises(ValidationError, match="ISO currency"):
        CandidateCreate.model_validate(
            candidate_payload(
                label="Keep the budget under 500",
                key="max_budget",
                operator="lte",
                value="500.00",
                unit="XYZ",
                category_scopes=["furniture"],
            )
        )

    with pytest.raises(ValidationError, match="decimal-string"):
        CandidateCreate.model_validate(
            candidate_payload(
                label="Keep the budget under $500",
                key="max_budget",
                operator="lte",
                value=500.0,
                unit="usd",
                category_scopes=["furniture"],
            )
        )


def test_structured_preference_needs_operator_and_patch_needs_mutation() -> None:
    with pytest.raises(ValidationError, match="require an operator"):
        CandidateCreate.model_validate(candidate_payload(key="max_height", operator=None))

    with pytest.raises(ValidationError, match="at least one preference field"):
        PreferencePatch.model_validate(
            {"expected_profile_version": 1, "expected_preference_revision": 1}
        )


def test_candidate_requires_exactly_one_explicit_local_source() -> None:
    requirement_id = str(uuid4())
    decision_product_id = str(uuid4())
    assert CandidateCreate.model_validate(candidate_payload()).source_requirement_id
    assert CandidateCreate.model_validate(
        candidate_payload(
            source_requirement_id=None,
            source_project_product_id=decision_product_id,
        )
    ).source_project_product_id
    with pytest.raises(ValidationError, match="exactly one"):
        CandidateCreate.model_validate(
            candidate_payload(
                source_requirement_id=requirement_id,
                source_project_product_id=decision_product_id,
            )
        )
