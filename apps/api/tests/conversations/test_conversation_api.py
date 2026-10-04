from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.conversations import service
from shopping.conversations.models import ConversationMessage, ProjectUpdateProposal
from shopping.integrations.personal_ai.fake import FakePersonalAIClient
from shopping.projects.models import ProjectRequirement

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


def test_oversized_project_context_is_saved_as_failure_without_provider_call(project_api):
    client, _owner, _engine = project_api
    fake = FakePersonalAIClient()
    set_fake(client, fake)
    response = client.post(
        "/projects",
        json={
            "title": "Vacuum",
            "goal": "Find a vacuum",
            "requirements": [
                {"kind": "preference", "label": f"Preference {index}", "detail": "x" * 1000}
                for index in range(30)
            ],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()

    accepted = send_message(client, project["id"], "oversized-context-key-0001")
    assert accepted.status_code == 202
    assistant = wait_for_message(client, project["id"], accepted.json()["assistant_message_id"])
    assert assistant["status"] == "failed"
    assert assistant["error_code"] == "context_too_large"
    assert fake.calls == 0
    current = client.get(f"/projects/{project['id']}").json()
    assert current["revision"] == 1
    assert len(current["requirements"]) == 30


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
    first = client.get(stream_url)
    second = client.get(stream_url)
    assert first.status_code == second.status_code == 200
    assert "event: snapshot" in first.text
    assert "event: complete" in first.text
    assert "event: complete" in second.text
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
