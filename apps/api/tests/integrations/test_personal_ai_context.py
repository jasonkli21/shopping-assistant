from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from shopping.config import Settings
from shopping.integrations.personal_ai import auth, context
from shopping.integrations.personal_ai.auth import get_personal_ai_context_owner
from shopping.integrations.personal_ai.context import (
    ContextReadRequest,
    ContextReadResponse,
    ContextRecord,
    ContextSourceRef,
    _bounded_response,
    _evidence_record,
    _observation_projections,
    _product_projection,
    _requirement_projection,
)
from shopping.projects.errors import ProjectError


def _context_request(**updates):
    values = {
        "project_id": uuid4(),
        "operation": "current",
        "fields": ("project_title", "requirements"),
        "max_results": 1,
        "max_bytes": 4096,
        **updates,
    }
    return ContextReadRequest(**values)


def test_context_contract_bounds_scope_and_operation_fields():
    request = _context_request()
    assert request.application_id == "shopping"
    assert request.workspace_id is None

    with pytest.raises(ValueError):
        _context_request(workspace_id="project-id")
    with pytest.raises(ValueError):
        _context_request(fields=("tax_id",))
    with pytest.raises(ValueError):
        _context_request(operation="search", selected_project_product_ids=())
    with pytest.raises(ValueError):
        _context_request(operation="verify", fields=("project_title",))
    product_id = uuid4()
    with pytest.raises(ValueError):
        _context_request(selected_project_product_ids=(product_id, product_id))
    with pytest.raises(ValueError):
        _context_request(selected_project_product_ids=tuple(uuid4() for _ in range(17)))
    with pytest.raises(ValueError):
        _context_request(max_results=51)
    with pytest.raises(ValueError):
        _context_request(max_bytes=65_537)


def test_project_permission_version_tracks_configured_identity_mapping(monkeypatch):
    settings = Settings(_env_file=None)
    settings.personal_ai_context_identity_mapping_reference = "owner-map-v1"
    settings.firebase_project_id = "health-project"
    settings.firebase_owner_uid = "firebase-owner"
    settings.personal_ai_context_user_audience = "personal-ai-client"
    settings.personal_ai_context_google_user_email = "owner@example.com"
    settings.personal_ai_context_google_user_subject = "google-subject-1"
    monkeypatch.setattr(context, "get_settings", lambda: settings)

    project_id = uuid4()
    first = context._project_permission(project_id, 4).version
    settings.personal_ai_context_identity_mapping_reference = "owner-map-v2"
    second = context._project_permission(project_id, 4).version
    assert second != first

    settings.personal_ai_context_google_user_subject = "google-subject-2"
    third = context._project_permission(project_id, 4).version
    assert third != second


def test_requirement_projection_keeps_hard_constraints_and_soft_preferences_distinct():
    classifications = {
        kind: _requirement_projection(
            SimpleNamespace(
                id=uuid4(),
                kind=kind,
                label=f"{kind} requirement",
                detail=None,
                attribute_key="weight",
                operator="lte",
                value=10,
                unit="lb",
                origin="owner",
                source_preference_id=None,
                source_preference_revision=None,
                source_preference_scope=None,
            )
        )["classification"]
        for kind in ("must_have", "constraint", "preference")
    }

    assert classifications == {
        "must_have": "hard",
        "constraint": "hard",
        "preference": "soft",
    }


def test_selected_project_product_projection_preserves_domain_identity_and_decision():
    project_product_id, product_id, variant_id = (str(uuid4()) for _ in range(3))
    projected = _product_projection(
        {
            "project_product_id": project_product_id,
            "product_id": product_id,
            "variant_id": variant_id,
            "canonical_name": "Example vacuum",
            "brand": "Example",
            "variant_name": "Model X, US",
            "identity_attributes": {"region": {"value": "US"}},
            "category_attributes": {"weight": {"value": 8, "unit": "lb"}},
            "product_revision": 2,
            "variant_revision": 3,
            "decision": {"state": "rejected", "rejection_reason": "too_heavy"},
        }
    )

    assert projected["project_product_id"] == project_product_id
    assert projected["product_id"] == product_id
    assert projected["variant_id"] == variant_id
    assert projected["product_revision"] == 2
    assert projected["variant_revision"] == 3
    assert projected["decision_state"] == "rejected"
    assert projected["saved"] is False
    assert projected["rejection_reason"] == "too_heavy"


def test_catalog_observations_keep_authority_source_and_freshness():
    now = datetime.now(UTC)
    observations = _observation_projections(
        {
            "offers": [
                {
                    "offer_id": str(uuid4()),
                    "source_url": "https://shop.example/item",
                    "retailer": "Example Shop",
                    "amount": "199.00",
                    "currency": "USD",
                    "availability": "in_stock",
                    "condition": "new",
                    "observed_at": (now - timedelta(minutes=1)).isoformat(),
                },
                {
                    "offer_id": str(uuid4()),
                    "source_url": "https://shop.example/old-item",
                    "retailer": "Example Shop",
                    "amount": "179.00",
                    "currency": "USD",
                    "availability": "unknown",
                    "condition": "unknown",
                    "observed_at": (now - timedelta(days=3)).isoformat(),
                },
            ],
            "claims": [
                {
                    "claim_id": str(uuid4()),
                    "snapshot_id": str(uuid4()),
                    "source_url": "https://maker.example/spec",
                    "source_title": "Specification",
                    "attribute_key": "weight",
                    "assertion": "Weight not stated",
                    "normalized_value": None,
                    "qualifiers": {},
                    "evidence_category": "manufacturer_specification",
                    "retrieved_at": now.isoformat(),
                    "published_at": None,
                }
            ],
        }
    )

    by_url = {item.get("source_url"): item for item in observations}
    current = by_url["https://shop.example/item"]
    stale = by_url["https://shop.example/old-item"]
    unknown = next(item for item in observations if item["kind"] == "evidence_claim")
    assert current["authority"] == "external_observation"
    assert current["freshness"] == "current"
    assert stale["freshness"] == "stale"
    assert unknown["freshness"] == "unknown"
    assert unknown["expires_at"] is None


def test_evidence_fingerprint_tracks_values_when_observation_identity_is_unchanged():
    project = SimpleNamespace(id=uuid4(), revision=3)
    product = {
        "project_product_id": str(uuid4()),
        "product_id": str(uuid4()),
        "product_revision": 4,
        "variant_id": str(uuid4()),
        "variant_revision": 9,
    }
    observed_at = datetime.now(UTC).isoformat()
    baseline = {
        "observation_id": str(uuid4()),
        "observed_at": observed_at,
        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        "source_url": "https://shop.example/item",
        "amount": "199.00",
    }
    changed = {**baseline, "amount": "189.00"}

    first = _evidence_record(project, product, baseline, ("catalog_observations",))
    second = _evidence_record(project, product, changed, ("catalog_observations",))

    assert first.source_version != second.source_version
    assert first.source_refs[-1].fingerprint != second.source_refs[-1].fingerprint
    assert first.expires_at == datetime.fromisoformat(baseline["expires_at"])
    projected = first.payload["catalog_observations"]
    assert projected["project_product_id"] == product["project_product_id"]
    assert projected["product_id"] == product["product_id"]
    assert projected["variant_id"] == product["variant_id"]
    assert projected["product_revision"] == product["product_revision"]
    assert projected["variant_revision"] == product["variant_revision"]


def test_context_response_enforces_serialized_byte_limit():
    record = ContextRecord(
        entity_type="project",
        entity_id=str(uuid4()),
        source_id="shopping-project:fixture",
        source_version="1",
        source_class="domain_current",
        authority="authoritative",
        sensitivity="sensitive",
        payload={"project_title": "A" * 1000},
        source_refs=(ContextSourceRef(kind="record", reference_id="fixture"),),
    )
    with pytest.raises(ProjectError) as raised:
        _bounded_response((record,), max_bytes=100, max_results=1)
    assert raised.value.code == "context_byte_limit"


class _FakeConnection:
    def __init__(self):
        self.statements = []

    def exec_driver_sql(self, statement):
        self.statements.append(statement)

    def execute(self, statement, params=None):
        self.statements.append((statement, params))


class _FakeSession(AbstractContextManager):
    def __init__(self, owner_id: UUID):
        self.owner_id = owner_id
        self.connection_value = _FakeConnection()
        self.execution_options = None
        self.closed = False

    def connection(self, execution_options=None):
        self.execution_options = execution_options
        return self.connection_value

    def scalar(self, _statement):
        return self.owner_id

    def __exit__(self, *_args):
        self.closed = True
        return False


def _request():
    return Request(
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": "/v1/integrations/personal-ai/context",
            "raw_path": b"/v1/integrations/personal-ai/context",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("test", 443),
        }
    )


def _auth_settings():
    return SimpleNamespace(
        personal_ai_context_enabled=True,
        auth_mode="firebase",
        firebase_owner_uid="firebase-owner",
        local_owner_id=UUID("00000000-0000-4000-8000-000000000001"),
        personal_ai_context_service_audience="https://shopping.example",
        personal_ai_context_service_account="personal-ai@example.iam.gserviceaccount.com",
        personal_ai_context_user_audience="personal-ai-web-client",
        personal_ai_context_google_user_email="owner@example.com",
        personal_ai_context_google_user_subject="google-subject-1",
        personal_ai_context_identity_mapping_reference="identity-map-review-42",
        personal_ai_context_timeout_seconds=3.0,
    )


def test_google_identity_verification_bounds_certificate_fetch_and_closes_session(monkeypatch):
    calls = []

    class FakeSession:
        closed = False

        def close(self):
            self.closed = True

    requests = []

    class FakeRequest:
        def __init__(self):
            self.session = FakeSession()
            requests.append(self)

        def __call__(self, _url, method="GET", body=None, headers=None, timeout=None, **_kwargs):
            calls.append(timeout)
            return None

    monkeypatch.setattr(auth, "GoogleRequest", FakeRequest)
    bounded_request_type = auth._bounded_google_request_type()
    monkeypatch.setattr(auth, "_bounded_google_request_type", lambda: bounded_request_type)

    def verify(_token, supplied_request, *, audience):
        supplied_request("https://www.googleapis.com/oauth2/v1/certs", timeout=60)
        return {"iss": "https://accounts.google.com", "email_verified": True}

    monkeypatch.setattr(auth.id_token, "verify_oauth2_token", verify)

    claims = auth._verify_google_identity_token("signed-token", audience="shopping-client")

    assert claims["email_verified"] is True
    assert calls == [3]
    assert len(requests) == 1 and requests[0].session.closed is True


def test_context_auth_separates_service_and_user_tokens_and_derives_fixed_owner(monkeypatch):
    settings = _auth_settings()
    verified = []

    def verify(token, *, audience):
        verified.append((token, audience))
        if token == "service-token":
            return {
                "iss": "https://accounts.google.com",
                "email": settings.personal_ai_context_service_account,
                "email_verified": True,
            }
        return {
            "iss": "https://accounts.google.com",
            "email": settings.personal_ai_context_google_user_email,
            "email_verified": True,
            "sub": settings.personal_ai_context_google_user_subject,
        }

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_verify_google_identity_token", verify)
    session = _FakeSession(settings.local_owner_id)
    request = _request()

    owner = get_personal_ai_context_owner(
        request,
        session,
        authorization="Bearer service-token",
        user_identity_token="user-token",
        application_id="shopping",
    )

    assert owner == settings.local_owner_id
    assert [audience for _token, audience in verified] == [
        "https://shopping.example",
        "personal-ai-web-client",
    ]
    assert session.execution_options == {"isolation_level": "REPEATABLE READ"}
    assert session.connection_value.statements[0] == "SET TRANSACTION READ ONLY"
    assert request.state.owner_key


def test_context_auth_rejects_unmapped_user_before_owner_lookup(monkeypatch):
    settings = _auth_settings()

    def verify(token, *, audience):
        if token == "service-token":
            return {
                "iss": "accounts.google.com",
                "email": settings.personal_ai_context_service_account,
                "email_verified": True,
            }
        return {
            "iss": "accounts.google.com",
            "email": settings.personal_ai_context_google_user_email,
            "email_verified": True,
            "sub": "different-google-subject",
        }

    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "_verify_google_identity_token", verify)
    session = _FakeSession(settings.local_owner_id)

    with pytest.raises(HTTPException) as raised:
        get_personal_ai_context_owner(
            _request(),
            session,
            authorization="Bearer service-token",
            user_identity_token="user-token",
            application_id="shopping",
        )

    assert raised.value.status_code == 403
    assert session.execution_options is None


def test_context_endpoint_caps_database_timeout_and_performs_read_only_projection(monkeypatch):
    from shopping.integrations.personal_ai import router as context_router

    owner_id = uuid4()
    session = _FakeSession(owner_id)
    settings = SimpleNamespace(personal_ai_context_timeout_seconds=1.5)
    monkeypatch.setattr(context_router, "get_settings", lambda: settings)
    monkeypatch.setattr(
        context_router,
        "read_context",
        lambda _session, _owner_id, _request: ContextReadResponse(items=()),
    )
    request = _context_request(timeout_seconds=4.0)

    response = context_router.read_personal_ai_context(request, session, owner_id)

    assert response.items == ()
    assert len(session.connection_value.statements) == 1
    statement, params = session.connection_value.statements[0]
    assert "statement_timeout" in str(statement)
    assert params == {"timeout": "1500ms"}


def test_context_auth_returns_not_found_without_verifying_when_disabled(monkeypatch):
    settings = _auth_settings()
    settings.personal_ai_context_enabled = False
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    session = _FakeSession(settings.local_owner_id)

    with pytest.raises(HTTPException) as raised:
        get_personal_ai_context_owner(_request(), session)

    assert raised.value.status_code == 404
    assert session.execution_options is None


def test_personal_ai_context_is_disabled_by_default_and_fails_closed_if_misconfigured():
    settings = Settings(_env_file=None)
    assert settings.personal_ai_context_enabled is False
    with pytest.raises(ValueError, match="personal_ai_context_identity_configuration_required"):
        Settings(_env_file=None, personal_ai_context_enabled=True)


@pytest.mark.db
def test_context_endpoint_returns_selected_state_and_bounded_evidence(project_api):
    from sqlalchemy.orm import Session

    from shopping.catalog.models import Product, ProductVariant, ProjectProduct, RetailOffer
    from shopping.integrations.personal_ai.auth import get_personal_ai_context_owner
    from shopping.main import app

    client, owner, engine = project_api
    created = client.post(
        "/projects",
        json={
            "title": "Vacuum project",
            "goal": "Find a quiet vacuum",
            "budget_maximum": "300.00",
            "budget_currency": "USD",
            "requirements": [
                {"kind": "must_have", "label": "HEPA filter"},
                {"kind": "preference", "label": "Lightweight"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    project = created.json()
    project_id = UUID(project["id"])
    product_id, variant_id, membership_id = uuid4(), uuid4(), uuid4()
    other_product_id, other_variant_id, other_membership_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        for p_id, v_id, pp_id, number in (
            (product_id, variant_id, membership_id, 1),
            (other_product_id, other_variant_id, other_membership_id, 2),
        ):
            session.add(
                Product(
                    id=p_id,
                    owner_id=owner["id"],
                    canonical_name=f"Vacuum {number}",
                    brand="Example",
                    category="vacuum",
                    revision=1,
                )
            )
            session.flush()
            session.add(
                ProductVariant(
                    id=v_id,
                    product_id=p_id,
                    display_name=f"Model {number}, US",
                    identity_key=f"model:{number}|region:us",
                    identity_attributes={"region": {"value": "US"}},
                    category_attributes={"weight": {"value": number * 5, "unit": "lb"}},
                    revision=1,
                )
            )
            session.flush()
            session.add(
                ProjectProduct(
                    id=pp_id,
                    project_id=project_id,
                    variant_id=v_id,
                    discovery_reason="Selected deterministic fixture",
                )
            )
        now = datetime.now(UTC)
        session.add_all(
            [
                RetailOffer(
                    owner_id=owner["id"],
                    variant_id=variant_id,
                    idempotency_key="context-current-offer-01",
                    retailer_name="Example Shop",
                    url="https://shop.example/current",
                    amount="249.00",
                    currency="USD",
                    availability="in_stock",
                    condition="new",
                    observed_at=now - timedelta(minutes=5),
                ),
                RetailOffer(
                    owner_id=owner["id"],
                    variant_id=variant_id,
                    idempotency_key="context-stale-offer-01",
                    retailer_name="Example Shop",
                    url="https://shop.example/stale",
                    amount="219.00",
                    currency="USD",
                    availability="unknown",
                    condition="unknown",
                    observed_at=now - timedelta(days=3),
                ),
                *[
                    RetailOffer(
                        owner_id=owner["id"],
                        variant_id=variant_id,
                        idempotency_key=f"context-recent-offer-{index}",
                        retailer_name="Example Shop",
                        url=f"https://shop.example/recent-{index}",
                        amount="239.00",
                        currency="USD",
                        availability="in_stock",
                        condition="new",
                        observed_at=now - timedelta(hours=index),
                    )
                    for index in range(1, 4)
                ],
                RetailOffer(
                    owner_id=owner["id"],
                    variant_id=variant_id,
                    idempotency_key="context-omitted-offer-01",
                    retailer_name="Example Shop",
                    url="https://shop.example/omitted",
                    amount="209.00",
                    currency="USD",
                    availability="unknown",
                    condition="unknown",
                    observed_at=now - timedelta(days=5),
                ),
            ]
        )
        session.commit()

    rejected = client.post(
        f"/projects/{project_id}/rejections/{membership_id}",
        json={
            "expected_version": 1,
            "request_key": "context-reject-selected-01",
            "reason": "Does not satisfy preference",
            "concerns": [],
            "rejection_reason": "too_heavy",
        },
    )
    assert rejected.status_code == 200, rejected.text
    app.dependency_overrides[get_personal_ai_context_owner] = lambda: owner["id"]
    path = "/v1/integrations/personal-ai/context"
    headers = {"X-Application-ID": "shopping"}

    current = client.post(
        path,
        headers=headers,
        json={
            "operation": "current",
            "project_id": str(project_id),
            "selected_project_product_ids": [str(membership_id)],
            "fields": ["project_title", "requirements", "budget_maximum", "selected_products"],
            "max_results": 1,
            "max_bytes": 32768,
        },
    )
    assert current.status_code == 200, current.text
    assert "no-store" in current.headers["cache-control"]
    assert current.json()["workspace_id"] is None
    project_context = current.json()["items"][0]
    assert project_context["source_class"] == "domain_current"
    assert project_context["authority"] == "authoritative"
    assert project_context["payload"]["budget_maximum"] == "300.00"
    requirements = project_context["payload"]["requirements"]
    assert [item["classification"] for item in requirements] == ["hard", "soft"]
    [selected] = project_context["payload"]["selected_products"]
    assert selected["project_product_id"] == str(membership_id)
    assert selected["product_id"] == str(product_id)
    assert selected["product_revision"] == 1
    assert selected["variant_id"] == str(variant_id)
    assert selected["variant_revision"] == 1
    assert selected["decision_state"] == "rejected"
    assert selected["saved"] is False
    assert selected["rejection_reason"] == "too_heavy"
    assert project_context["permission_dependencies"][0]["permission_id"] == (
        f"shopping_project_read:{project_id}"
    )
    product_dependency = next(
        item
        for item in project_context["permission_dependencies"]
        if item["permission_id"].startswith("shopping_product_read:")
    )
    original_product_version = product_dependency["version"]
    project_revision_before_refresh = client.get(f"/projects/{project_id}").json()["revision"]
    with Session(engine) as session:
        variant = session.get(ProductVariant, variant_id)
        variant.category_attributes = {"weight": {"value": 4, "unit": "lb"}}
        variant.revision += 1
        session.commit()
    verify_product = client.post(
        path,
        headers=headers,
        json={
            "operation": "verify",
            "project_id": str(project_id),
            "selected_project_product_ids": [str(membership_id)],
            "fields": ["selected_products"],
            "max_results": 1,
            "max_bytes": 8192,
        },
    )
    assert verify_product.status_code == 200, verify_product.text
    [verified_product] = verify_product.json()["items"]
    refreshed_product_dependency = next(
        item
        for item in verified_product["permission_dependencies"]
        if item["permission_id"] == product_dependency["permission_id"]
    )
    assert refreshed_product_dependency["version"] != original_product_version
    refreshed_project = client.get(f"/projects/{project_id}").json()
    assert refreshed_project["revision"] == project_revision_before_refresh
    refreshed_current = client.post(
        path,
        headers=headers,
        json={
            "operation": "current",
            "project_id": str(project_id),
            "selected_project_product_ids": [str(membership_id)],
            "fields": ["project_title", "selected_products"],
            "max_results": 1,
            "max_bytes": 16384,
        },
    )
    assert refreshed_current.status_code == 200, refreshed_current.text
    refreshed_version = refreshed_current.json()["items"][0]["source_version"]
    assert refreshed_version != project_context["source_version"]

    search = client.post(
        path,
        headers=headers,
        json={
            "operation": "search",
            "project_id": str(project_id),
            "selected_project_product_ids": [str(membership_id)],
            "fields": ["catalog_observations"],
            "max_results": 10,
            "max_bytes": 32768,
        },
    )
    assert search.status_code == 200, search.text
    evidence_records = search.json()["items"]
    assert len(evidence_records) == 5
    assert all(item["entity_type"] == "evidence" for item in evidence_records)
    assert all(item["entity_id"] == str(membership_id) for item in evidence_records)
    assert all(item["source_class"] == "external_research" for item in evidence_records)
    assert all(item["authority"] == "external" for item in evidence_records)
    assert all(len(item["source_refs"]) == 5 for item in evidence_records)
    observations = [
        item["payload"]["catalog_observations"]["observations"][0] for item in evidence_records
    ]
    assert {item["freshness"] for item in observations} == {"current", "stale"}
    assert all(item["authority"] == "external_observation" for item in observations)
    assert all(item["partial_result"] is True for item in evidence_records)
    assert all(item["omitted_count"] == 1 for item in evidence_records)
    assert all(
        record["expires_at"]
        == record["payload"]["catalog_observations"]["observations"][0]["expires_at"]
        for record in evidence_records
    )
    current_expiry = max(
        datetime.fromisoformat(record["expires_at"])
        for record in evidence_records
        if record["payload"]["catalog_observations"]["observations"][0]["freshness"] == "current"
    )
    stale_expiry = next(
        datetime.fromisoformat(record["expires_at"])
        for record in evidence_records
        if record["payload"]["catalog_observations"]["observations"][0]["freshness"] == "stale"
    )
    assert stale_expiry < current_expiry
    assert (
        client.get(f"/projects/{project_id}").json()["revision"]
        == rejected.json()["event"]["project_version"]
    )

    owner["id"] = uuid4()
    forbidden = client.post(
        path,
        headers=headers,
        json={
            "operation": "current",
            "project_id": str(project_id),
            "fields": ["project_title"],
            "max_results": 1,
            "max_bytes": 4096,
        },
    )
    assert forbidden.status_code == 404
