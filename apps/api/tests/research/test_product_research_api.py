from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.evidence.models import (
    AssessmentCitation,
    Claim,
    ClaimEvidence,
    ClaimRelation,
    ProductAssessment,
    ResearchRunSource,
    Source,
    SourceSnapshot,
)
from shopping.extraction.fake import FakePageRetriever
from shopping.extraction.retriever import RetrievedDocument
from shopping.projects.models import ShoppingProject
from shopping.research.models import (
    DiscoveryCandidate,
    ResearchRun,
    ResearchRunTarget,
    ResearchStageAttempt,
    SearchQueryRecord,
)
from shopping.search.fake import FakeSearchProvider
from shopping.search.provider import SearchResult

pytestmark = pytest.mark.db


def _create_project(client):
    response = client.post(
        "/projects",
        json={
            "title": "Vacuum evaluation",
            "goal": "Find a vacuum that works well for pet hair",
            "category": "Vacuum",
            "requirements": [{"kind": "must_have", "label": "Good pet hair pickup"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _seed_project_product(project, owner, engine):
    product_id, variant_id, project_product_id = uuid4(), uuid4(), uuid4()
    with Session(engine) as session:
        session.add(
            Product(
                id=product_id,
                owner_id=owner["id"],
                canonical_name="Clean Vacuum",
                brand="Acme",
                category="Vacuum",
                model_family="AX-4",
            )
        )
        session.flush()
        session.add(
            ProductVariant(
                id=variant_id,
                product_id=product_id,
                display_name="AX-4 HEPA",
                identity_key="region=us",
                identity_attributes={"region": "US"},
                category_attributes={"filter": "HEPA"},
            )
        )
        session.add(
            ProjectProduct(
                id=project_product_id,
                project_id=UUID(project["id"]),
                variant_id=variant_id,
                discovery_reason="Selected for product research",
            )
        )
        session.commit()
    return product_id, variant_id, project_product_id


def _wait_for_run(client, project_id, run_id, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/projects/{project_id}/research/{run_id}")
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] in {"succeeded", "partial", "failed", "interrupted", "canceled"}:
            return run
        time.sleep(0.01)
    raise AssertionError("product research did not reach a terminal state")


def test_product_research_persists_targeted_source_snapshot_without_candidates(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    product_id, variant_id, project_product_id = _seed_project_product(project, owner, engine)
    query = "Acme Clean Vacuum AX-4 AX-4 HEPA manufacturer specifications"
    url = "https://acme.example/ax-4/specifications"
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {query: [SearchResult(title="AX-4 Specifications", url=url, snippet="HEPA filter")]}
    )
    body = """<!doctype html><html><head><title>Acme AX-4 specifications</title>
    <meta property="article:published_time" content="2025-02-03T12:00:00Z"></head>
    <body><h1>Acme AX-4 HEPA</h1><p>Product specifications.</p>
    <p>Measured runtime is 60 minutes in normal mode.</p></body></html>"""
    document = RetrievedDocument(
        requested_url=url,
        final_url=url,
        content_type="text/html; charset=utf-8",
        body=body,
        content_hash=hashlib.sha256(body.encode()).hexdigest(),
        retrieved_at=datetime.now(UTC),
        decoded_bytes=len(body.encode()),
    )
    client.app.state.discovery_supervisor.page_retriever = FakePageRetriever({url: document})
    request = {
        "objective": "Research runtime and suitability for pet hair",
        "type": "product_research",
        "request_key": "product-research-run-001",
        "expected_version": project["revision"],
        "selected_project_product_ids": [str(project_product_id)],
        "budgets": {"max_products": 5, "max_sources_per_product": 12},
    }

    accepted = client.post(f"/projects/{project['id']}/research", json=request)
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["type"] == "product_research"
    assert run["status"] == "partial", run
    assert run["candidates_found"] == 0
    assert run["results_found"] == 1
    assert run["effective_budgets"]["max_products"] == 3
    assert run["effective_budgets"]["max_sources_per_product"] == 4
    assert run["queries"][0]["target_project_product_id"] == str(project_product_id)
    assert run["targets"] == [
        {
            "project_product_id": str(project_product_id),
            "product_id": str(product_id),
            "variant_id": str(variant_id),
            "status": "partial",
            "sources_attempted": 1,
            "sources_retrieved": 1,
            "claims_created": 0,
            "error_code": "no_grounded_claims",
        }
    ]

    with Session(engine) as session:
        stored_run = session.get(ResearchRun, UUID(run["id"]))
        assert stored_run.run_type == "product_research"
        assert session.scalars(select(DiscoveryCandidate)).all() == []
        target = session.scalar(
            select(ResearchRunTarget).where(ResearchRunTarget.research_run_id == stored_run.id)
        )
        attempt = session.scalar(
            select(ResearchRunSource).where(ResearchRunSource.research_run_id == stored_run.id)
        )
        source = session.get(Source, attempt.source_id)
        snapshot = session.get(SourceSnapshot, attempt.snapshot_id)
        assert target.product_revision == 1
        assert target.variant_revision == 1
        assert attempt.status == "retrieved"
        assert snapshot.content_hash == document.content_hash
        assert snapshot.published_at == datetime(2025, 2, 3, 12, tzinfo=UTC)
        assert "60 minutes" in snapshot.relevant_text
        assert source.classification == "manufacturer_specification"

    replay = client.post(f"/projects/{project['id']}/research", json=request)
    assert replay.status_code == 202
    assert replay.json() == {"run_id": run["id"], "status": "partial", "replayed": True}


def test_product_research_rejects_non_member_project_product(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    _product_id, _variant_id, _project_product_id = _seed_project_product(project, owner, engine)
    request = {
        "objective": "Inspect this product",
        "type": "product_research",
        "request_key": "product-research-owner-001",
        "expected_version": project["revision"],
        "selected_project_product_ids": [str(uuid4())],
    }
    response = client.post(f"/projects/{project['id']}/research", json=request)
    assert response.status_code == 404
    assert client.get(f"/projects/{project['id']}/research?limit=20").json()["items"] == []


def test_product_research_assesses_all_one_hundred_requirements(project_api):
    client, owner, engine = project_api
    requirements = [
        {
            "kind": "must_have",
            "label": f"Requirement {index:03d}: " + "specific criterion " * 6,
            "detail": "Saved context that must survive planning and assessment. " * 22,
        }
        for index in range(100)
    ]
    response = client.post(
        "/projects",
        json={
            "title": "Large requirement set",
            "goal": "Assess every saved constraint",
            "category": "Vacuum",
            "requirements": requirements,
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Check each requirement",
            "type": "product_research",
            "request_key": "product-research-one-hundred-requirements",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
        },
    )
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "failed"
    with Session(engine) as session:
        assessment = session.scalar(select(ProductAssessment))
        assert len(assessment.requirements_snapshot) == 100
        assert len(assessment.conclusions) == 100
        assert len(json.dumps(assessment.requirements_snapshot).encode()) > 24_000
        assert len(json.dumps(assessment.conclusions).encode()) > 12_000
        assert all(item["status"] == "unknown" for item in assessment.conclusions)


def test_malformed_planner_output_is_terminal_and_inspectable(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    client.app.state.discovery_supervisor.client.task_fixtures = {
        "plan_product_research.v1": {"*": {"queries": "not a list"}}
    }
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Check runtime",
            "type": "product_research",
            "request_key": "product-research-malformed-plan",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
        },
    )
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "failed"
    assert run["error_code"] == "malformed_response"
    assert run["targets"][0]["status"] in {"failed", "skipped"}
    assert run["stages"] == [
        {
            "stage": "planning",
            "target_project_product_id": None,
            "source_snapshot_id": None,
            "attempt_number": 1,
            "status": "failed",
            "error_code": "malformed_response",
            "validation_warnings": [],
        }
    ]
    with Session(engine) as session:
        assert session.scalar(select(ProductAssessment)) is not None


def test_canceled_product_planner_cannot_persist_late_plan(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    client.app.state.discovery_supervisor.client.delay_seconds = 0.4
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Check runtime",
            "type": "product_research",
            "request_key": "product-research-cancel-plan",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
        },
    )
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = client.get(f"/projects/{project['id']}/research/{run_id}").json()
        if any(
            stage["stage"] == "planning" and stage["status"] == "running" for stage in run["stages"]
        ):
            break
        time.sleep(0.01)
    else:
        raise AssertionError("planner stage did not start")
    canceled = client.post(f"/projects/{project['id']}/research/{run_id}/cancel")
    assert canceled.status_code == 200, canceled.text
    assert canceled.json()["run"]["status"] == "canceled"
    assert canceled.json()["run"]["stages"][0]["status"] == "canceled"
    with Session(engine) as session:
        assert session.scalars(select(SearchQueryRecord)).all() == []
        assert session.scalar(select(ProductAssessment)) is None
        stage = session.scalar(select(ResearchStageAttempt))
        assert stage.status == "canceled"


def test_exhausted_ai_budget_records_skipped_extraction_stage(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    query = "Acme Clean Vacuum AX-4 AX-4 HEPA manufacturer specifications"
    url = "https://acme.example/ax-4/specifications"
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {query: [SearchResult(title="AX-4 specifications", url=url, snippet="Runtime")]}
    )
    body = "<h1>Acme AX-4 HEPA</h1><p>Technical specifications. Runtime: 60 minutes.</p>"
    client.app.state.discovery_supervisor.page_retriever = FakePageRetriever(
        {
            url: RetrievedDocument(
                requested_url=url,
                final_url=url,
                content_type="text/html",
                body=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
                retrieved_at=datetime.now(UTC),
                decoded_bytes=len(body.encode()),
            )
        }
    )
    client.app.state.discovery_supervisor.client.task_fixtures = {
        "plan_product_research.v1": {
            "*": {
                "queries": [
                    {
                        "project_product_id": str(project_product_id),
                        "text": query,
                        "purpose": "Find manufacturer specifications.",
                        "source_class": "manufacturer_specification",
                    }
                ]
            }
        }
    }
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Check runtime",
            "type": "product_research",
            "request_key": "product-research-ai-budget",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
            "budgets": {"max_ai_calls": 1},
        },
    )
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "partial"
    assert run["targets"][0]["error_code"] == "ai_call_budget_exhausted"
    extraction = next(stage for stage in run["stages"] if stage["stage"] == "extraction")
    assert extraction["status"] == "skipped"
    assert extraction["error_code"] == "ai_call_budget_exhausted"
    with Session(engine) as session:
        assert session.scalar(select(ProductAssessment)) is not None


def test_over_budget_response_records_failed_attempt_without_source_snapshot(project_api):
    client, owner, engine = project_api
    project = _create_project(client)
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    query = "Acme Clean Vacuum AX-4 AX-4 HEPA manufacturer specifications"
    url = "https://acme.example/ax-4/oversized"
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {query: [SearchResult(title="AX-4 Specifications", url=url, snippet="Runtime")]}
    )
    body = "<h1>AX-4 HEPA</h1><p>60 minutes runtime.</p>"
    client.app.state.discovery_supervisor.page_retriever = FakePageRetriever(
        {
            url: RetrievedDocument(
                requested_url=url,
                final_url=url,
                content_type="text/html",
                body=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
                retrieved_at=datetime.now(UTC),
                decoded_bytes=len(body.encode()),
            )
        }
    )
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Check runtime",
            "type": "product_research",
            "request_key": "product-research-byte-limit-001",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
            "budgets": {"max_total_bytes": 1},
        },
    )
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "failed"
    with Session(engine) as session:
        attempt = session.scalar(select(ResearchRunSource))
        assert attempt.status == "failed"
        assert attempt.reason == "byte_budget_exceeded"
        assert attempt.bytes_read == len(body.encode())
        assert attempt.snapshot_id is None
        assert session.scalars(select(SourceSnapshot)).all() == []
        assert session.scalars(select(Claim)).all() == []


def test_product_research_persists_grounded_claim_and_cited_assessment(project_api):
    client, owner, engine = project_api
    response = client.post(
        "/projects",
        json={
            "title": "Vacuum runtime",
            "goal": "Find a cordless vacuum with adequate runtime",
            "category": "Vacuum",
            "requirements": [
                {
                    "kind": "must_have",
                    "label": "At least 40 minutes runtime",
                    "attribute_key": "runtime",
                    "operator": "gte",
                    "value": 40,
                    "unit": "min",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    _product_id, variant_id, project_product_id = _seed_project_product(project, owner, engine)
    query = "Acme Clean Vacuum AX-4 AX-4 HEPA manufacturer specifications"
    url = "https://acme.example/ax-4/runtime"
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {query: [SearchResult(title="AX-4 Specifications", url=url, snippet="Runtime")]}
    )
    body = "<h1>Acme AX-4 HEPA US</h1><p>60 minutes runtime in normal mode.</p>"
    client.app.state.discovery_supervisor.page_retriever = FakePageRetriever(
        {
            url: RetrievedDocument(
                requested_url=url,
                final_url=url,
                content_type="text/html",
                body=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
                retrieved_at=datetime.now(UTC),
                decoded_bytes=len(body.encode()),
            )
        }
    )
    client.app.state.discovery_supervisor.client.task_fixtures = {
        "extract_claims.v1": {
            url: {
                "claims": [
                    {
                        "attribute_key": "runtime",
                        "quote": "60 minutes runtime in normal mode.",
                        "context_quote": "AX-4 HEPA US 60 minutes runtime in normal mode.",
                        "normalized_value": 60,
                        "unit": "min",
                        "qualifiers": {"mode": "normal"},
                        "measurement_details": {},
                        "extraction_confidence": "high",
                    }
                ],
                "explanation": "One source-backed runtime claim.",
            }
        }
    }
    request = {
        "objective": "Check runtime",
        "type": "product_research",
        "request_key": "product-research-claim-001",
        "expected_version": project["revision"],
        "selected_project_product_ids": [str(project_product_id)],
    }
    accepted = client.post(f"/projects/{project['id']}/research", json=request)
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "succeeded"
    assert run["targets"][0]["claims_created"] == 1
    assert any(
        stage["stage"] == "extraction" and stage["status"] == "succeeded" for stage in run["stages"]
    )
    with Session(engine) as session:
        claim = session.scalar(select(Claim))
        evidence = session.scalar(select(ClaimEvidence))
        assessment = session.scalar(select(ProductAssessment))
        citation = session.scalar(select(AssessmentCitation))
        assert claim.subject_variant_id == variant_id
        assert evidence.claim_id == claim.id
        assert evidence.excerpt == claim.assertion_text
        assert assessment.conclusions[0]["status"] == "supports"
        assert assessment.conclusions[0]["claim_ids"] == [str(claim.id)]
        assert citation.claim_id == claim.id
        claim_id, snapshot_id = claim.id, claim.snapshot_id
    research = client.get(f"/projects/{project['id']}/products/{project_product_id}/research")
    assert research.json()["latest_run_id"] == run["id"]
    assert research.json()["has_more_assessments"] is False
    selected_history = client.get(
        f"/projects/{project['id']}/products/{project_product_id}/research",
        params={"research_run_id": run["id"], "assessment_offset": 0},
    )
    assert selected_history.status_code == 200
    assert selected_history.json()["claims"] == research.json()["claims"]
    assert selected_history.json()["has_more_claims"] is False
    assert selected_history.json()["has_more_sources"] is False
    older_claims = client.get(
        f"/projects/{project['id']}/products/{project_product_id}/research",
        params={"research_run_id": run["id"], "claim_offset": 20},
    )
    assert older_claims.status_code == 200
    assert older_claims.json()["claims"] == []
    assert older_claims.json()["state"] == "researched"
    older_sources = client.get(
        f"/projects/{project['id']}/products/{project_product_id}/research",
        params={"research_run_id": run["id"], "source_offset": 20},
    )
    assert older_sources.status_code == 200
    assert older_sources.json()["sources"] == []
    assert older_sources.json()["state"] == "researched"
    invalid_page = client.get(
        f"/projects/{project['id']}/products/{project_product_id}/research",
        params={"assessment_offset": 1},
    )
    assert invalid_page.status_code == 422
    invalid_claim_page = client.get(
        f"/projects/{project['id']}/products/{project_product_id}/research",
        params={"claim_offset": 1},
    )
    assert invalid_claim_page.status_code == 422
    assert research.status_code == 200, research.text
    assert research.json()["state"] == "researched"
    assert research.json()["assessments"][0]["conclusions"][0]["claim_ids"] == [str(claim_id)]
    detail = client.get(f"/projects/{project['id']}/claims/{claim_id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["evidence_excerpt"] == "60 minutes runtime in normal mode."
    assert detail.json()["content_hash"] == hashlib.sha256(body.encode()).hexdigest()
    source_detail = client.get(f"/projects/{project['id']}/sources/{snapshot_id}")
    assert source_detail.status_code == 200, source_detail.text
    assert source_detail.json()["claims"][0]["id"] == str(claim_id)
    product_sources = client.get(f"/products/{_product_id}/sources?variant_id={variant_id}")
    assert product_sources.status_code == 200, product_sources.text
    assert product_sources.json()["sources"][0]["snapshot_id"] == str(snapshot_id)
    other_project = _create_project(client)
    assert client.get(f"/projects/{other_project['id']}/claims/{claim_id}").status_code == 404
    with Session(engine) as session:
        project_row = session.get(ShoppingProject, UUID(project["id"]))
        project_row.revision += 1
        session.commit()
    stale = client.get(f"/projects/{project['id']}/products/{project_product_id}/research")
    assert stale.json()["assessments"][0]["context_stale"] is True
    replay = client.post(f"/projects/{project['id']}/research", json=request)
    assert replay.json()["replayed"] is True
    with Session(engine) as session:
        assert len(session.scalars(select(Claim)).all()) == 1


def test_runtime_contexts_retain_both_quotes_and_cite_only_comparable_result(project_api):
    client, owner, engine = project_api
    response = client.post(
        "/projects",
        json={
            "title": "Runtime comparison",
            "goal": "Find at least 40 minutes of runtime",
            "category": "Vacuum",
            "requirements": [
                {
                    "kind": "must_have",
                    "label": "At least 40 minutes runtime",
                    "attribute_key": "runtime",
                    "operator": "gte",
                    "value": 40,
                    "unit": "min",
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    project = response.json()
    _product_id, _variant_id, project_product_id = _seed_project_product(project, owner, engine)
    query = "Acme Clean Vacuum AX-4 AX-4 HEPA manufacturer specifications"
    marketing_url = "https://acme.example/ax-4/specifications"
    measured_url = "https://www.rtings.com/vacuum/reviews/ax-4"
    client.app.state.discovery_supervisor.search_provider = FakeSearchProvider(
        {
            query: [
                SearchResult(title="AX-4 specifications", url=marketing_url, snippet="Runtime"),
                SearchResult(
                    title="AX-4 runtime test", url=measured_url, snippet="Measured runtime"
                ),
            ]
        }
    )
    bodies = {
        marketing_url: "<h1>Acme AX-4 HEPA US</h1><p>Up to 60 minutes runtime in eco mode.</p>",
        measured_url: "<h1>AX-4 HEPA US runtime test</h1>"
        "<p>Measured 37 minutes in normal mode.</p>",
    }
    client.app.state.discovery_supervisor.page_retriever = FakePageRetriever(
        {
            url: RetrievedDocument(
                requested_url=url,
                final_url=url,
                content_type="text/html",
                body=body,
                content_hash=hashlib.sha256(body.encode()).hexdigest(),
                retrieved_at=datetime.now(UTC),
                decoded_bytes=len(body.encode()),
            )
            for url, body in bodies.items()
        }
    )
    client.app.state.discovery_supervisor.client.task_fixtures = {
        "extract_claims.v1": {
            marketing_url: {
                "claims": [
                    {
                        "attribute_key": "runtime",
                        "quote": "Up to 60 minutes runtime in eco mode.",
                        "context_quote": "AX-4 HEPA US Up to 60 minutes runtime in eco mode.",
                        "normalized_value": 60,
                        "unit": "min",
                        "qualifiers": {"mode": "eco", "limit": "up_to"},
                    }
                ]
            },
            measured_url: {
                "claims": [
                    {
                        "attribute_key": "runtime",
                        "quote": "Measured 37 minutes in normal mode.",
                        "context_quote": (
                            "AX-4 HEPA US runtime test Measured 37 minutes in normal mode."
                        ),
                        "normalized_value": 37,
                        "unit": "min",
                        "qualifiers": {"mode": "normal"},
                    }
                ]
            },
        }
    }
    accepted = client.post(
        f"/projects/{project['id']}/research",
        json={
            "objective": "Compare runtime contexts",
            "type": "product_research",
            "request_key": "product-research-context-001",
            "expected_version": project["revision"],
            "selected_project_product_ids": [str(project_product_id)],
        },
    )
    assert accepted.status_code == 202, accepted.text
    run = _wait_for_run(client, project["id"], accepted.json()["run_id"])
    assert run["status"] == "succeeded"
    assert run["targets"][0]["claims_created"] == 2
    with Session(engine) as session:
        claims = session.scalars(select(Claim).order_by(Claim.assertion_text)).all()
        assert len(claims) == 2
        relation = session.scalar(select(ClaimRelation))
        assert relation.relation == "different_context"
        assessment = session.scalar(select(ProductAssessment))
        conclusion = assessment.conclusions[0]
        assert conclusion["status"] == "conflicts"
        measured = next(claim for claim in claims if claim.normalized_value == 37)
        assert conclusion["claim_ids"] == [str(measured.id)]
        for claim in claims:
            evidence = session.scalar(
                select(ClaimEvidence).where(ClaimEvidence.claim_id == claim.id)
            )
            assert evidence.excerpt == claim.assertion_text
            snapshot = session.get(SourceSnapshot, claim.snapshot_id)
            assert (
                snapshot.relevant_text[evidence.locator["start"] : evidence.locator["end"]]
                == evidence.excerpt
            )
