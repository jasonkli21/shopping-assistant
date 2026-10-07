from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.conversations import service
from shopping.conversations.models import ConversationMessage, ProjectUpdateProposal
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.main import logger as application_logger
from shopping.projects.models import ProjectRequirement, UserNote

pytestmark = pytest.mark.db


def create_project(client: TestClient) -> dict:
    response = client.post(
        "/projects",
        json={"title": "Vacuum", "goal": "Find a vacuum for pet hair"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def set_fake(client: TestClient, fake: FakePersonalAIClient) -> None:
    client.app.state.generation_supervisor.client = fake


def add_project_product(engine, owner_id: UUID, project_id: UUID, number: int) -> UUID:
    product_id, variant_id, membership_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        product = Product(
            id=product_id,
            owner_id=owner_id,
            canonical_name=f"Vacuum {number}",
            brand="Example",
            category="vacuum",
            revision=1,
        )
        session.add(product)
        session.flush()
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                display_name=f"Model {number}, US",
                identity_key=f"model:{number}|region:us",
                identity_attributes={"region": {"value": "US"}},
                category_attributes={},
                revision=1,
            )
        )
        session.flush()
        session.add(
            ProjectProduct(
                id=membership_id,
                project_id=project_id,
                variant_id=variant_id,
                discovery_reason="Created by a deterministic proposal fixture",
            )
        )
        session.commit()
    return membership_id


def send_message(
    client: TestClient, project_id: str, key: str, text: str = "Find a vacuum good with hair"
):
    return client.post(
        f"/projects/{project_id}/messages",
        json={"text": text, "request_key": key, "expected_version": 1},
    )


def wait_for_message(
    client: TestClient, project_id: str, message_id: str, timeout: float = 3.0
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/projects/{project_id}/messages?limit=100")
        assert response.status_code == 200, response.text
        message = next(
            (item for item in response.json()["items"] if item["id"] == message_id), None
        )
        if message and message["status"] != "generating":
            return message
        time.sleep(0.01)
    raise AssertionError("assistant generation did not reach a terminal state")


def test_message_replay_proposal_apply_and_replay_after_later_edit(project_api):
    client, _owner, engine = project_api
    fake = FakePersonalAIClient()
    set_fake(client, fake)
    project = create_project(client)

    accepted = send_message(client, project["id"], "phase2-request-key-0001")
    assert accepted.status_code == 202, accepted.text
    assistant_id = accepted.json()["assistant_message_id"]
    assistant = wait_for_message(client, project["id"], assistant_id)
    assert assistant["status"] == "completed"
    assert assistant["proposal"]["status"] == "pending"
    with Session(engine) as session:
        assert session.get(ConversationMessage, UUID(assistant_id)).input_snapshot is None
    proposal_id = assistant["proposal"]["id"]
    assert fake.calls == 1

    latest_page = client.get(f"/projects/{project['id']}/messages?limit=1").json()
    assert [item["role"] for item in latest_page["items"]] == ["assistant"]
    assert latest_page["next_cursor"] is not None
    earlier_page = client.get(
        f"/projects/{project['id']}/messages?limit=1&before={latest_page['next_cursor']}"
    ).json()
    assert [item["role"] for item in earlier_page["items"]] == ["user"]
    assert earlier_page["next_cursor"] is None

    unchanged = client.get(f"/projects/{project['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["requirements"] == []

    barrier = Barrier(2)

    def apply_proposal():
        barrier.wait()
        return client.post(
            f"/projects/{project['id']}/proposals/{proposal_id}/apply",
            json={"expected_version": 1},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        applies = list(executor.map(lambda _index: apply_proposal(), range(2)))
    assert all(response.status_code == 200 for response in applies)
    assert sorted(response.json()["replayed"] for response in applies) == [False, True]
    applied = next(response for response in applies if not response.json()["replayed"])
    assert applied.json()["project"]["revision"] == 2
    assert applied.json()["project"]["requirements"][0]["origin"] == "ai_confirmed"
    assert applied.json()["proposal"]["status"] == "applied"
    applied_at = applied.json()["proposal"]["applied_at"]
    assert applied_at is not None

    replay = client.post(
        f"/projects/{project['id']}/proposals/{proposal_id}/apply",
        json={"expected_version": 1},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["project"]["revision"] == 2

    later_edit = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 2, "goal": "Find a quiet vacuum"},
    )
    assert later_edit.status_code == 200
    assert later_edit.json()["revision"] == 3
    saved_replay = client.post(
        f"/projects/{project['id']}/proposals/{proposal_id}/apply",
        json={"expected_version": 3},
    )
    assert saved_replay.status_code == 200
    assert saved_replay.json()["replayed"] is True
    assert saved_replay.json()["project"]["revision"] == 2
    assert saved_replay.json()["proposal"]["applied_at"] == applied_at
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 3

    replayed_command = send_message(client, project["id"], "phase2-request-key-0001")
    assert replayed_command.status_code == 202
    assert replayed_command.json()["replayed"] is True
    assert replayed_command.json()["user_message_id"] == accepted.json()["user_message_id"]
    mismatch = client.post(
        f"/projects/{project['id']}/messages",
        json={
            "text": "Different text",
            "request_key": "phase2-request-key-0001",
            "expected_version": 1,
        },
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "idempotency_conflict"
    assert fake.calls == 1

    with Session(engine) as session:
        rows = list(session.scalars(select(ProjectRequirement)).all())
        proposals = list(session.scalars(select(ProjectUpdateProposal)).all())
        assert len(rows) == 1
        assert len(proposals) == 1
        assert rows[0].origin == "ai_confirmed"


@pytest.mark.parametrize("final_state", ["pending", "dismissed", "applied"])
def test_proposal_lifecycle_checks_owner_and_live_project_before_replay(project_api, final_state):
    client, owner, _engine = project_api
    set_fake(
        client,
        FakePersonalAIClient(
            response={
                "assistant_message": "I captured the category for review.",
                "clarification_questions": [],
                "project_updates": {"category": "Vacuum"},
                "requirement_operations": [],
            }
        ),
    )
    project = create_project(client)
    accepted = send_message(client, project["id"], f"lifecycle-{final_state}-key-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    proposal_id = assistant["proposal"]["id"]
    proposal_url = f"/projects/{project['id']}/proposals/{proposal_id}"
    if final_state == "dismissed":
        dismissed = client.post(f"{proposal_url}/dismiss")
        assert dismissed.status_code == 200
    elif final_state == "applied":
        applied = client.post(f"{proposal_url}/apply", json={"expected_version": 1})
        assert applied.status_code == 200
        assert applied.json()["proposal"]["applied_at"] is not None

    original_owner = owner["id"]
    owner["id"] = uuid4()
    assert client.post(f"{proposal_url}/apply", json={"expected_version": 1}).status_code == 404
    assert client.post(f"{proposal_url}/dismiss").status_code == 404
    owner["id"] = original_owner

    current = client.get(f"/projects/{project['id']}").json()
    deleted = client.delete(f"/projects/{project['id']}?expected_version={current['revision']}")
    assert deleted.status_code == 204
    assert (
        client.post(
            f"{proposal_url}/apply", json={"expected_version": current["revision"]}
        ).status_code
        == 404
    )
    assert client.post(f"{proposal_url}/dismiss").status_code == 404


def test_invalid_persisted_proposal_operation_rolls_back_project_write(project_api):
    client, _owner, engine = project_api
    set_fake(
        client,
        FakePersonalAIClient(
            response={
                "assistant_message": "I prepared a suggestion.",
                "clarification_questions": [],
                "project_updates": {"category": "Vacuum"},
                "requirement_operations": [],
            }
        ),
    )
    project = create_project(client)
    accepted = send_message(client, project["id"], "invalid-proposal-operation-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    proposal_id = UUID(assistant["proposal"]["id"])
    with Session(engine) as session:
        proposal = session.get(ProjectUpdateProposal, proposal_id)
        assert proposal is not None
        proposal.operations = {
            "project_updates": {"category": "Vacuum"},
            "requirement_operations": [
                {
                    "operation": "add",
                    "fields": {"kind": "unsupported", "label": "invalid"},
                }
            ],
        }
        session.commit()

    rejected = client.post(
        f"/projects/{project['id']}/proposals/{proposal_id}/apply",
        json={"expected_version": 1},
    )
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "proposal_invalid"
    unchanged = client.get(f"/projects/{project['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["category"] is None
    assert unchanged["requirements"] == []
    with Session(engine) as session:
        persisted = session.get(ProjectUpdateProposal, proposal_id)
        assert persisted is not None
        assert persisted.status == "pending"


def test_phase6_proposal_applies_decision_note_and_comparison_atomically(project_api):
    client, owner, engine = project_api
    project = create_project(client)
    first = add_project_product(engine, owner["id"], UUID(project["id"]), 1)
    second = add_project_product(engine, owner["id"], UUID(project["id"]), 2)
    with Session(engine) as session:
        session.add(
            UserNote(
                owner_id=owner["id"],
                project_id=UUID(project["id"]),
                project_product_id=first,
                text="Existing rationale",
                version=1,
            )
        )
        session.commit()
    set_fake(
        client,
        FakePersonalAIClient(
            response={
                "assistant_message": "I prepared your decision workspace changes for review.",
                "operations": [
                    {
                        "operation": "shortlist",
                        "project_product_id": str(first),
                        "reason": "Fits the entryway storage limit.",
                    },
                    {
                        "operation": "add_note",
                        "project_product_id": str(first),
                        "text": "Measure the entryway before ordering.",
                    },
                    {
                        "operation": "add_note",
                        "project_product_id": str(first),
                        "text": "Confirm the outlet location.",
                    },
                    {
                        "operation": "set_comparison_dimensions",
                        "project_product_ids": [str(first), str(second)],
                        "dimensions": [
                            {
                                "key": "width",
                                "label": "Width",
                                "dimension_type": "fact",
                            }
                        ],
                        "title": "Entryway fit",
                        "display_mode": "differences",
                    },
                ],
            }
        ),
    )

    accepted = send_message(
        client,
        project["id"],
        "phase6-proposal-workspace-0001",
        "Shortlist one and compare the options.",
    )
    assert accepted.status_code == 202, accepted.text
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    proposal_id = assistant["proposal"]["id"]
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 1
    assert (
        client.get(f"/projects/{project['id']}/products/{first}/decision").json()["state"]
        == "considering"
    )

    applied = client.post(
        f"/projects/{project['id']}/proposals/{proposal_id}/apply",
        json={"expected_version": 1},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["project"]["revision"] == 2
    assert (
        client.get(f"/projects/{project['id']}/products/{first}/decision").json()["state"]
        == "shortlisted"
    )
    assert client.get(f"/projects/{project['id']}/products/{first}/notes").json()["text"] == (
        "Existing rationale\n\nMeasure the entryway before ordering.\n\n"
        "Confirm the outlet location."
    )
    comparisons = client.get(f"/projects/{project['id']}/comparisons").json()["items"]
    assert len(comparisons) == 1
    assert comparisons[0]["project_revision"] == 2
    assert comparisons[0]["dimensions"][0]["key"] == "width"


def test_proposal_can_replace_an_item_at_the_requirement_limit(project_api):
    client, _owner, _engine = project_api
    project_response = client.post(
        "/projects",
        json={
            "title": "Vacuum",
            "goal": "Find a vacuum",
            "requirements": [
                {"kind": "preference", "label": f"Preference {index}"} for index in range(100)
            ],
        },
    )
    assert project_response.status_code == 201, project_response.text
    project = project_response.json()
    removed_id = project["requirements"][0]["id"]
    set_fake(
        client,
        FakePersonalAIClient(
            response={
                "assistant_message": "I prepared a replacement requirement.",
                "clarification_questions": [],
                "project_updates": {},
                "requirement_operations": [
                    {
                        "operation": "add",
                        "fields": {"kind": "preference", "label": "Replacement preference"},
                    },
                    {"operation": "remove", "id": removed_id},
                ],
            }
        ),
    )

    accepted = send_message(client, project["id"], "full-requirement-replacement-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "completed"
    assert assistant["proposal"]["status"] == "pending"
    applied = client.post(
        f"/projects/{project['id']}/proposals/{assistant['proposal']['id']}/apply",
        json={"expected_version": 1},
    )

    assert applied.status_code == 200, applied.text
    requirements = applied.json()["project"]["requirements"]
    assert len(requirements) == 100
    assert removed_id not in {item["id"] for item in requirements}
    replacement = next(item for item in requirements if item["label"] == "Replacement preference")
    assert replacement["origin"] == "ai_confirmed"


def test_concurrent_exact_message_commands_share_one_durable_generation(project_api):
    client, _owner, engine = project_api
    fake = FakePersonalAIClient(delay_seconds=0.12)
    set_fake(client, fake)
    project = create_project(client)
    barrier = Barrier(2)

    def submit():
        barrier.wait()
        return send_message(client, project["id"], "concurrent-replay-key-0001")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: submit(), range(2)))
    assert [response.status_code for response in responses] == [202, 202]
    assert len({response.json()["user_message_id"] for response in responses}) == 1
    assert sorted(response.json()["replayed"] for response in responses) == [False, True]
    wait_for_message(client, project["id"], responses[0].json()["assistant_message_id"])
    assert fake.calls == 1
    with Session(engine) as session:
        users = list(
            session.scalars(
                select(ConversationMessage).where(ConversationMessage.role == "user")
            ).all()
        )
        assert len(users) == 1


@pytest.mark.parametrize(
    ("scenario", "error_code"),
    [
        ("malformed", "invalid_output"),
        ("foreign_id", "invalid_output"),
        ("invalid_budget", "invalid_output"),
        ("refusal", "provider_refused"),
    ],
)
def test_invalid_or_refused_output_never_creates_a_proposal(project_api, scenario, error_code):
    client, _owner, engine = project_api
    set_fake(client, FakePersonalAIClient(scenario=scenario))
    project = create_project(client)
    accepted = send_message(client, project["id"], f"failure-key-{scenario}-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == error_code
    assert assistant["proposal"] is None
    with Session(engine) as session:
        assert session.get(ConversationMessage, UUID(assistant["id"])).input_snapshot is None
    unchanged = client.get(f"/projects/{project['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["requirements"] == []


@pytest.mark.parametrize(
    "output",
    [
        {
            "assistant_message": "Budget understood.",
            "project_updates": {"budget_maximum": "400", "budget_currency": "ZZZ"},
        },
        {
            "assistant_message": "Requirement updated.",
            "requirement_operations": [
                {"operation": "update", "id": "requirement", "fields": {"label": None}}
            ],
        },
        {
            "assistant_message": "Requirement updated.",
            "requirement_operations": [
                {
                    "operation": "update",
                    "id": "requirement",
                    "fields": {
                        "attribute_key": "noise",
                        "operator": "eq",
                        "value": "x" * 3000,
                    },
                }
            ],
        },
        {
            "assistant_message": "Requirement updated.",
            "requirement_operations": [
                {
                    "operation": "update",
                    "id": "requirement",
                    "fields": {
                        "attribute_key": "noise",
                        "operator": "eq",
                        "value": [[[[[["deep"]]]]]],
                    },
                }
            ],
        },
        {
            "assistant_message": "Requirement updated.",
            "requirement_operations": [
                {"operation": "update", "id": "requirement", "fields": {"kind": "maybe"}}
            ],
        },
        {
            "assistant_message": "Requirement added.",
            "requirement_operations": [
                {"operation": "add", "fields": {"kind": "preference", "label": "   "}}
            ],
        },
        {
            "assistant_message": "Budget understood.",
            "project_updates": {"budget_maximum": "400", "budget_currency": "US1"},
        },
        {
            "assistant_message": "Budget understood.",
            "project_updates": {"budget_maximum": "４００", "budget_currency": "USD"},
        },
    ],
    ids=[
        "unsupported-currency",
        "null-required-label",
        "oversized-criterion-value",
        "deep-criterion-json",
        "unknown-requirement-enum",
        "blank-added-label",
        "invalid-currency-code",
        "non-ascii-money",
    ],
)
def test_invalid_phase_one_fields_fail_generation_without_proposal_or_revision(project_api, output):
    client, _owner, engine = project_api
    created = client.post(
        "/projects",
        json={
            "title": "Vacuum",
            "goal": "Find a vacuum",
            "requirements": [
                {
                    "kind": "must_have",
                    "label": "Quiet operation",
                    "attribute_key": "noise",
                    "operator": "lte",
                    "value": 50,
                    "unit": "dB",
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()
    response = {
        **output,
        "assistant_message": output["assistant_message"],
        "clarification_questions": [],
        "project_updates": output.get("project_updates", {}),
        "requirement_operations": [
            {**operation, "id": str(project["requirements"][0]["id"])}
            if operation.get("id") == "requirement"
            else operation
            for operation in output.get("requirement_operations", [])
        ],
    }
    set_fake(client, FakePersonalAIClient(response=response))
    accepted = send_message(client, project["id"], f"invalid-field-{project['id']}")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == "invalid_output"
    assert assistant["proposal"] is None
    unchanged = client.get(f"/projects/{project['id']}").json()
    assert unchanged["revision"] == 1
    assert unchanged["requirements"] == project["requirements"]
    with Session(engine) as session:
        proposals = list(session.scalars(select(ProjectUpdateProposal)).all())
        assert proposals == []


def test_maximum_valid_project_context_is_compacted_for_provider(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient()
    set_fake(client, fake)
    response = client.post(
        "/projects",
        json={
            "title": "Vacuum",
            "goal": "Find a vacuum",
            "requirements": [
                {
                    "kind": "constraint" if index % 2 else "preference",
                    "label": (f"Preference {index}: " + "criterion " * 28)[:300],
                    "detail": "saved project note " * 100,
                    "attribute_key": "max_height",
                    "operator": "lte",
                    "value": index + 1,
                    "unit": "cm",
                }
                for index in range(100)
            ],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()

    accepted = send_message(
        client,
        project["id"],
        "maximum-context-key-00001",
        text="Help me understand the requirements.",
    )
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "completed", assistant
    assert assistant["error_code"] is None
    assert fake.calls == 1
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 1
    assert len(current["requirements"]) == 100
    assert current["requirements"] == project["requirements"]


def test_noncompressible_project_context_is_saved_as_failure_without_provider_call(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient()
    set_fake(client, fake)
    requirements = [
        {
            "kind": "constraint",
            "label": f"Supported mode set {index}",
            "attribute_key": "supported_modes",
            "operator": "one_of",
            "value": [f"mode-{index}-" + "x" * 1900 for _ in range(4)],
        }
        for index in range(10)
    ]
    response = client.post(
        "/projects",
        json={"title": "Vacuum", "goal": "Find a vacuum", "requirements": requirements},
    )
    assert response.status_code == 201, response.text
    project = response.json()

    accepted = send_message(client, project["id"], "noncompressible-context-key-01")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == "context_too_large"
    assert fake.calls == 0
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 1
    assert current["requirements"] == project["requirements"]


def test_timeout_is_persisted_and_retry_is_a_new_command(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient(delay_seconds=0.15)
    set_fake(client, fake)
    client.app.state.generation_supervisor.timeout_seconds = 0.02
    project = create_project(client)
    accepted = send_message(client, project["id"], "timeout-request-key-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == "provider_timeout"

    retry = client.post(
        f"/projects/{project['id']}/messages",
        json={
            "text": "Find a vacuum good with hair",
            "request_key": "timeout-retry-key-0001",
            "expected_version": 1,
        },
    )
    assert retry.status_code == 202
    assert retry.json()["user_message_id"] != accepted.json()["user_message_id"]


def test_generation_is_single_per_conversation_and_reconnect_attaches_only(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient(delay_seconds=0.15)
    set_fake(client, fake)
    project = create_project(client)
    accepted = send_message(client, project["id"], "concurrent-request-key-0001")
    assert accepted.status_code == 202

    competing = send_message(client, project["id"], "concurrent-request-key-0002")
    assert competing.status_code == 409
    assert competing.json()["error"]["code"] == "conversation_busy"

    stream_url = (
        f"/projects/{project['id']}/messages/stream"
        f"?message_id={accepted.json()['assistant_message_id']}"
    )
    log_output = StringIO()
    handler = logging.StreamHandler(log_output)
    application_logger.addHandler(handler)
    try:
        first = client.get(stream_url)
        second = client.get(stream_url)
    finally:
        application_logger.removeHandler(handler)
    assert first.status_code == second.status_code == 200
    assert "event: snapshot" in first.text
    assert "event: complete" in first.text
    assert "event: complete" in second.text
    stream_events = [
        json.loads(line)
        for line in log_output.getvalue().splitlines()
        if json.loads(line).get("event") == "http_stream"
    ]
    assert len(stream_events) == 2, log_output.getvalue()
    assert all(item["duration_ms"] >= 0 and item["request_id"] for item in stream_events)
    assert "concurrent-request-key-0001" not in log_output.getvalue()
    assert fake.calls == 1
    messages = client.get(f"/projects/{project['id']}/messages?limit=100").json()["items"]
    assert len([message for message in messages if message["role"] == "user"]) == 1


def test_slow_generation_finishes_without_any_stream_subscriber(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient(delay_seconds=0.12)
    set_fake(client, fake)
    project = create_project(client)
    accepted = send_message(client, project["id"], "detached-request-key-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "completed"
    assert fake.calls == 1


def test_restart_marks_durable_generation_interrupted(project_api):
    client, owner, engine = project_api
    project = create_project(client)
    with Session(engine) as session:
        reserved = service.create_message_command(
            session,
            owner["id"],
            UUID(project["id"]),
            text="Find a vacuum",
            request_key="restart-request-key-0001",
            expected_version=1,
        )
    supervisor = client.app.state.generation_supervisor
    assert supervisor.recover_after_restart() == 1
    message = wait_for_message(client, project["id"], str(reserved.response.assistant_message_id))
    assert message["status"] == "interrupted"
    assert message["error_code"] == "generation_interrupted"


def test_stale_proposal_conflicts_without_project_mutation(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient(delay_seconds=0.15)
    set_fake(client, fake)
    project = create_project(client)
    accepted = send_message(client, project["id"], "stale-request-key-0001")
    assert accepted.status_code == 202
    updated = client.patch(
        f"/projects/{project['id']}",
        json={"expected_version": 1, "goal": "Find a quiet vacuum"},
    )
    assert updated.status_code == 200
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["proposal"]["status"] == "stale"
    response = client.post(
        f"/projects/{project['id']}/proposals/{assistant['proposal']['id']}/apply",
        json={"expected_version": 2},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_stale"
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 2
    assert current["goal"] == "Find a quiet vacuum"
    assert current["requirements"] == []


def test_owner_scoped_history_proposal_and_stream(project_api):
    client, owner, _engine = project_api
    fake = FakePersonalAIClient()
    set_fake(client, fake)
    project = create_project(client)
    accepted = send_message(client, project["id"], "scope-request-key-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    original_owner = owner["id"]
    owner["id"] = uuid4()
    assert client.get(f"/projects/{project['id']}/messages").status_code == 404
    assert (
        client.get(
            f"/projects/{project['id']}/messages/stream?message_id={assistant['id']}"
        ).status_code
        == 404
    )
    owner["id"] = original_owner
    proposal_url = f"/projects/{project['id']}/proposals/{assistant['proposal']['id']}"
    dismissed = client.post(f"{proposal_url}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["proposal"]["status"] == "dismissed"
    replay = client.post(f"{proposal_url}/dismiss")
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert client.get(f"/projects/{project['id']}").json()["revision"] == 1
    applied = client.post(f"{proposal_url}/apply", json={"expected_version": 1})
    assert applied.status_code == 409
    assert applied.json()["error"]["code"] == "proposal_dismissed"
    owner["id"] = uuid4()
    assert (
        client.post(
            f"/projects/{project['id']}/proposals/{assistant['proposal']['id']}/dismiss"
        ).status_code
        == 404
    )
