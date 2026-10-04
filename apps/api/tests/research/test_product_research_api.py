from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopping.catalog.models import Product, ProductVariant, ProjectProduct
from shopping.evidence.models import ResearchRunSource, Source, SourceSnapshot
from shopping.extraction.fake import FakePageRetriever
from shopping.extraction.retriever import RetrievedDocument
from shopping.research.models import DiscoveryCandidate, ResearchRun, ResearchRunTarget
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
    <body><h1>AX-4 HEPA</h1><p>Measured runtime is 60 minutes in normal mode.</p></body></html>"""
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
    assert run["status"] == "succeeded"
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
            "status": "succeeded",
            "sources_attempted": 1,
            "sources_retrieved": 1,
            "claims_created": 0,
            "error_code": None,
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
    assert replay.json() == {"run_id": run["id"], "status": "succeeded", "replayed": True}


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
