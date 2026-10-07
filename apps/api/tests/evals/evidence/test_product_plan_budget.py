import copy
import json
from uuid import uuid4

import pytest

from shopping.research.product_task import MAX_CONTEXT_CHARS, build_request


def test_full_requirement_snapshot_stays_plannable_without_dropping_assessment_data():
    requirements = []
    for index in range(100):
        requirements.append(
            {
                "id": str(uuid4()),
                "label": f"Requirement {index}: " + "important detail " * 14,
                "detail": "long saved notes " * 100,
                "kind": "constraint" if index % 2 else "preference",
                "attribute_key": "runtime",
                "operator": "gte",
                "value": index + 1,
                "unit": "min",
                "preference_origin": (
                    {
                        "preference_id": str(uuid4()),
                        "preference_revision": 3,
                        "scope": ["vacuum", "home"],
                    }
                    if index % 2 == 0
                    else None
                ),
            }
        )
    snapshot = {
        "objective": "Find evidence for this vacuum",
        "project": {"goal": "Vacuum for apartment", "category": "vacuum"},
        "selected_products": [
            {
                "project_product_id": str(uuid4()),
                "variant_name": "AX-4",
                "identity_attributes": {"region": "US", "voltage": "120V"},
            }
        ],
        "requirements": requirements,
    }
    original_snapshot = copy.deepcopy(snapshot)

    request = build_request(snapshot, 8)
    repeated_request = build_request(snapshot, 8)
    encoded_request = json.dumps(
        {"task": request.task, "input": request.input},
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )

    assert len(encoded_request) <= MAX_CONTEXT_CHARS
    assert repeated_request == request
    assert len(request.input["context"]["requirements"]) == 100
    compacted = request.input["context"]["requirements"]
    for source, planned in zip(requirements, compacted, strict=True):
        for field in (
            "id",
            "kind",
            "attribute_key",
            "operator",
            "value",
            "unit",
        ):
            assert planned[field] == source[field]
        if source["preference_origin"] is None:
            assert "preference_origin" not in planned
        else:
            assert planned["preference_origin"] == {
                "id": source["preference_origin"]["preference_id"],
                "revision": source["preference_origin"]["preference_revision"],
                "scope": source["preference_origin"]["scope"],
            }
    assert any(item["label"].endswith("…") for item in compacted)
    assert all(item["detail"] is None or item["detail"].endswith("…") for item in compacted)
    assert (
        request.input["context"]["selected_products"][0]["project_product_id"]
        == snapshot["selected_products"][0]["project_product_id"]
    )
    assert request.input["context"]["selected_products"][0]["identity_attributes"] == {
        "region": "US",
        "voltage": "120V",
    }
    assert len(snapshot["requirements"][0]["detail"]) > 1000
    assert snapshot == original_snapshot


def test_noncompressible_structured_requirement_values_fail_closed():
    snapshot = {
        "objective": "Plan source searches",
        "project": {"goal": "Find a product", "category": "vacuum"},
        "selected_products": [{"project_product_id": str(uuid4()), "product_name": "Vacuum"}],
        "requirements": [
            {
                "id": str(uuid4()),
                "kind": "constraint",
                "label": f"Requirement {index}",
                "detail": "Optional detail" * 100,
                "attribute_key": "supported_modes",
                "operator": "one_of",
                "value": [f"mode-{index}-" + "x" * 1900 for _ in range(4)],
                "unit": None,
                "preference_origin": None,
            }
            for index in range(4)
        ],
    }

    with pytest.raises(ValueError, match="configured size limit"):
        build_request(snapshot, 8)
