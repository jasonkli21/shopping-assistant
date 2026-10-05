from uuid import uuid4

from shopping.research.product_task import MAX_CONTEXT_CHARS, build_request


def test_full_requirement_snapshot_stays_plannable_without_dropping_assessment_data():
    requirements = [
        {
            "id": str(uuid4()),
            "label": f"Requirement {index}: " + "important detail " * 20,
            "detail": "long saved notes " * 100,
            "kind": "constraint",
            "attribute_key": "runtime",
        }
        for index in range(100)
    ]
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

    request = build_request(snapshot, 8)

    assert len(str(request.input["context"])) < MAX_CONTEXT_CHARS
    assert len(str(request.input)) < MAX_CONTEXT_CHARS
    assert len(request.input["context"]["requirements"]) == 100
    assert (
        request.input["context"]["selected_products"][0]["project_product_id"]
        == snapshot["selected_products"][0]["project_product_id"]
    )
    assert request.input["context"]["selected_products"][0]["identity_attributes"] == {
        "region": "US",
        "voltage": "120V",
    }
    assert len(snapshot["requirements"][0]["detail"]) > 1000
