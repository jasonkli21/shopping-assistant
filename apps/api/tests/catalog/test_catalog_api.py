from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from shopping.catalog.models import (
    CatalogObservation,
    EntityResolutionEvent,
    Product,
    ProductVariant,
    ProjectProduct,
    RetailOffer,
)
from shopping.extraction.fake import FakePageRetriever
from shopping.extraction.retriever import RetrievedDocument
from shopping.extraction.task import FakeCatalogExtractionTask
from shopping.research.models import DiscoveryCandidate, ResearchRun

pytestmark = pytest.mark.db

FIXTURES = json.loads(
    Path(__file__).parents[1].joinpath("evals/normalization/catalog_extractions.json").read_text()
)


class CountingRetriever(FakePageRetriever):
    def __init__(self, documents):
        super().__init__(documents)
        self.calls = 0
        self.lock = Lock()

    async def retrieve(self, url):
        with self.lock:
            self.calls += 1
        time.sleep(0.02)
        return await super().retrieve(url)


def _document(url: str, body: str) -> RetrievedDocument:
    encoded = body.encode()
    return RetrievedDocument(
        requested_url=url,
        final_url=url,
        content_type="text/html; charset=utf-8",
        body=body,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        retrieved_at=datetime.now(UTC),
    )


def _install_fixtures(project_api, fixture_indexes: list[int]):
    client, _owner, _engine = project_api
    documents = {
        FIXTURES[index]["url"]: _document(FIXTURES[index]["url"], FIXTURES[index]["page"])
        for index in fixture_indexes
    }
    outputs = {FIXTURES[index]["url"]: FIXTURES[index]["extraction"] for index in fixture_indexes}
    retriever = CountingRetriever(documents)
    from shopping.main import app

    app.state.catalog_page_retriever = retriever
    app.state.catalog_extraction_task = FakeCatalogExtractionTask(outputs)
    return client, retriever


def _seed_candidate(project_api, url: str, name: str = "Candidate vacuum"):
    client, owner, engine = project_api
    project_response = client.post(
        "/projects",
        json={"title": "Vacuum research", "goal": "Find a vacuum", "category": "vacuum"},
    )
    assert project_response.status_code == 201, project_response.text
    project_id = UUID(project_response.json()["id"])
    candidate_id, run_id = uuid4(), uuid4()
    with Session(engine) as session:
        session.add(
            ResearchRun(
                id=run_id,
                project_id=project_id,
                owner_id=owner["id"],
                objective="Find a vacuum",
                run_type="discovery",
                status="succeeded",
                request_key="seed-research-request",
                request_hash="1" * 64,
                snapshot_revision=1,
                input_snapshot={},
                effective_budgets={},
                task_name="plan_discovery.v1",
                prompt_version="fixture.v1",
                schema_version=1,
                ai_provider="fake",
                search_provider="fake",
            )
        )
        session.flush()
        session.add(
            DiscoveryCandidate(
                id=candidate_id,
                project_id=project_id,
                run_id=run_id,
                provisional_name=name,
                brand_clue="Acme",
                model_clue="AX-400",
                category_clue="vacuum",
                discovery_reason="Found in a search result.",
                normalized_url=url,
            )
        )
        session.commit()
    return project_response.json(), candidate_id


def _normalize(client, project, candidate_id, *, key, catalog_version, project_version):
    return client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/normalize",
        json={
            "request_key": key,
            "expected_catalog_version": catalog_version,
            "expected_project_version": project_version,
        },
    )


def test_retailer_observations_share_exact_variant_append_offers_and_replay(project_api):
    client, _retriever = _install_fixtures(project_api, [0, 1])
    project, first_candidate = _seed_candidate(project_api, FIXTURES[0]["url"])
    first = _normalize(
        client,
        project,
        first_candidate,
        key="normalize-retailer-a-0001",
        catalog_version=1,
        project_version=1,
    )
    assert first.status_code == 200, first.text
    first_result = first.json()
    assert first_result["status"] == "auto_linked"
    assert (first_result["catalog_version"], first_result["project_version"]) == (2, 2)

    second_project = {**project, "revision": first_result["project_version"]}
    with Session(project_api[2]) as session:
        second_candidate_id = uuid4()
        session.add(
            DiscoveryCandidate(
                id=second_candidate_id,
                project_id=UUID(project["id"]),
                run_id=session.scalar(
                    select(ResearchRun.id).where(ResearchRun.project_id == UUID(project["id"]))
                ),
                provisional_name="Acme Clean 4 from retailer B",
                discovery_reason="Second retailer result.",
                normalized_url=FIXTURES[1]["url"],
            )
        )
        session.commit()
    second = _normalize(
        client,
        second_project,
        second_candidate_id,
        key="normalize-retailer-b-0001",
        catalog_version=2,
        project_version=2,
    )
    assert second.status_code == 200, second.text
    second_result = second.json()
    assert second_result["product_id"] == first_result["product_id"]
    assert second_result["variant_id"] == first_result["variant_id"]
    assert second_result["project_version"] == 3

    replay = _normalize(
        client,
        project,
        first_candidate,
        key="normalize-retailer-a-0001",
        catalog_version=1,
        project_version=1,
    )
    assert replay.status_code == 200, replay.text
    replayed = replay.json()
    assert replayed["replayed"] is True
    assert replayed["event_id"] == first_result["event_id"]
    assert (replayed["catalog_version"], replayed["project_version"]) == (2, 2)

    offers = client.get(
        f"/products/{first_result['product_id']}/offers",
        params={"variant_id": first_result["variant_id"]},
    )
    assert offers.status_code == 200, offers.text
    assert [item["amount"] for item in offers.json()["items"]] == ["319.00", "299.99"]
    assert [item["currency"] for item in offers.json()["items"]] == ["USD", "USD"]
    with Session(project_api[2]) as session:
        assert session.scalar(select(func.count()).select_from(CatalogObservation)) == 2
        assert session.scalar(select(func.count()).select_from(RetailOffer)) == 2
        assert session.scalar(select(func.count()).select_from(ProjectProduct)) == 1

    owner = project_api[1]
    owner["id"] = uuid4()
    assert client.get(f"/products/{first_result['product_id']}").status_code == 404
    hidden_offers = client.get(
        f"/products/{first_result['product_id']}/offers",
        params={"variant_id": first_result["variant_id"]},
    )
    assert hidden_offers.status_code == 404
    assert client.get("/products", params={"q": "Acme"}).json()["items"] == []


def test_bundle_region_and_unknown_dimensions_remain_distinct(project_api):
    fixture_indexes = [0, 2, 3, 4, 5]
    client, retriever = _install_fixtures(project_api, fixture_indexes)
    project, body_candidate_id = _seed_candidate(project_api, FIXTURES[2]["url"])

    def normalize(index: int, candidate_id: UUID, catalog_version: int, project_version: int):
        return _normalize(
            client,
            {**project, "revision": project_version},
            candidate_id,
            key=f"variant-dimensions-{index:02d}-0001",
            catalog_version=catalog_version,
            project_version=project_version,
        )

    first = normalize(2, body_candidate_id, 1, 1)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "auto_linked"

    candidates = {}
    with Session(project_api[2]) as session:
        run_id = session.scalar(
            select(ResearchRun.id).where(ResearchRun.project_id == UUID(project["id"]))
        )
        for index in (3, 0, 4, 5):
            candidate_id = uuid4()
            candidates[index] = candidate_id
            session.add(
                DiscoveryCandidate(
                    id=candidate_id,
                    project_id=UUID(project["id"]),
                    run_id=run_id,
                    provisional_name=FIXTURES[index]["extraction"]["product_name"],
                    discovery_reason="Variant identity fixture.",
                    normalized_url=FIXTURES[index]["url"],
                )
            )
        session.commit()

    retrievals_before_conflict = retriever.calls
    reused_key = _normalize(
        client,
        {**project, "revision": body["project_version"]},
        candidates[3],
        key="variant-dimensions-02-0001",
        catalog_version=body["catalog_version"],
        project_version=body["project_version"],
    )
    assert reused_key.status_code == 409
    assert reused_key.json()["error"]["code"] == "request_key_reused"
    assert retriever.calls == retrievals_before_conflict

    results = {}
    catalog_version, project_version = body["catalog_version"], body["project_version"]
    for index in (3, 0, 4, 5):
        response = normalize(index, candidates[index], catalog_version, project_version)
        assert response.status_code == 200, response.text
        results[index] = response.json()
        catalog_version = results[index]["catalog_version"]
        project_version = results[index]["project_version"]

    kit = results[3]
    unknown = results[0]
    monitor_us = results[4]
    monitor_eu = results[5]
    assert kit["status"] == "auto_linked"
    assert kit["product_id"] == body["product_id"]
    assert kit["variant_id"] != body["variant_id"]
    assert kit["reason"] == "created_distinct_variant_for_known_family"
    assert unknown["status"] == "unresolved"
    assert unknown["variant_id"] is None
    assert unknown["reason"] == "unknown_variant_dimensions"
    assert monitor_us["product_id"] == monitor_eu["product_id"]
    assert monitor_us["variant_id"] != monitor_eu["variant_id"]
    assert catalog_version == 6
    assert project_version == 5

    products = client.get(f"/projects/{project['id']}/products")
    assert products.status_code == 200, products.text
    assert len(products.json()["items"]) == 4
    with Session(project_api[2]) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 2
        assert session.scalar(select(func.count()).select_from(ProductVariant)) == 4


def test_correction_refresh_and_revert_preserve_mapping_and_offer_provenance(project_api):
    client, retriever = _install_fixtures(project_api, [0])
    project, candidate_id = _seed_candidate(project_api, FIXTURES[0]["url"])
    normalized = _normalize(
        client,
        project,
        candidate_id,
        key="normalize-before-correction-0001",
        catalog_version=1,
        project_version=1,
    )
    assert normalized.status_code == 200, normalized.text
    original = normalized.json()

    correction_body = {
        "request_key": "manual-correction-0001",
        "expected_catalog_version": 2,
        "expected_project_version": 2,
        "reason": "This result is the complete pet kit.",
        "new_product": {
            "canonical_name": "Acme Clean 4 Pet Kit",
            "brand": "Acme",
            "category": "vacuum",
            "model_family": "AX-400",
            "variant_name": "Pet kit",
            "identity_attributes": {"bundle": "pet kit"},
        },
    }
    correction = client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/correction",
        json=correction_body,
    )
    assert correction.status_code == 200, correction.text
    correction_result = correction.json()
    assert correction_result["status"] == "manual_linked"
    assert correction_result["previous_project_product_id"] == original["project_product_id"]
    corrected_mapping = correction_result["selected_project_product_id"]
    assert corrected_mapping != original["project_product_id"]

    replay = client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/correction",
        json=correction_body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["replayed"] is True
    assert replay.json()["event_id"] == correction_result["event_id"]

    refresh = _normalize(
        client,
        {**project, "revision": correction_result["project_version"]},
        candidate_id,
        key="normalize-after-correction-0001",
        catalog_version=correction_result["catalog_version"],
        project_version=correction_result["project_version"],
    )
    assert refresh.status_code == 200, refresh.text
    assert refresh.json()["project_product_id"] == corrected_mapping
    assert refresh.json()["reason"] == "manual_mapping_preserved"
    assert retriever.calls == 2

    revert = client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/correction/revert",
        json={
            "request_key": "manual-revert-0001",
            "expected_catalog_version": refresh.json()["catalog_version"],
            "expected_project_version": refresh.json()["project_version"],
        },
    )
    assert revert.status_code == 200, revert.text
    assert revert.json()["status"] == "reverted"
    assert revert.json()["selected_project_product_id"] == original["project_product_id"]

    candidate_page = client.get(f"/projects/{project['id']}/candidates")
    assert candidate_page.status_code == 200, candidate_page.text
    candidate_row = next(
        item for item in candidate_page.json()["items"] if item["id"] == str(candidate_id)
    )
    state = candidate_row["normalization"]
    assert state["status"] == "reverted"
    assert state["variant_id"] == original["variant_id"]

    offers = client.get(
        f"/products/{original['product_id']}/offers",
        params={"variant_id": original["variant_id"]},
    )
    assert offers.status_code == 200, offers.text
    assert len(offers.json()["items"]) == 1
    with Session(project_api[2]) as session:
        manual_variant = session.scalar(
            select(ProductVariant)
            .join(ProjectProduct, ProjectProduct.variant_id == ProductVariant.id)
            .where(ProjectProduct.id == UUID(corrected_mapping))
        )
        assert manual_variant is not None
        assert manual_variant.identity_attributes["bundle"]["origin"] == "user_correction"
        assert session.scalar(select(func.count()).select_from(EntityResolutionEvent)) == 4
        assert session.scalar(select(func.count()).select_from(RetailOffer)) == 1


def test_unsupported_page_stays_a_candidate_without_normalized_facts(project_api):
    client, _retriever = _install_fixtures(project_api, [])
    project, candidate_id = _seed_candidate(project_api, "https://example.test/category")
    from shopping.main import app

    app.state.catalog_page_retriever = FakePageRetriever(
        {
            "https://example.test/category": _document(
                "https://example.test/category", "No product data"
            )
        }
    )
    unsupported = client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/normalize",
        json={
            "request_key": "unsupported-normalization-0001",
            "expected_catalog_version": 1,
            "expected_project_version": 1,
        },
    )
    assert unsupported.status_code == 200, unsupported.text
    assert unsupported.json()["status"] == "unsupported"
    assert unsupported.json()["failure_code"] == "no_fixture"
    assert unsupported.json()["product_id"] is None
    candidate = client.get(f"/projects/{project['id']}/candidates").json()["items"][0]
    assert candidate["normalization"]["latest_observation_status"] == "unsupported"
    with Session(project_api[2]) as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 0


def test_private_candidate_url_is_blocked_before_network_and_owner_scoped(project_api):
    from shopping.extraction.http_retriever import HTTPPageRetriever
    from shopping.main import app

    client, owner, engine = project_api
    project, candidate_id = _seed_candidate(project_api, "http://127.0.0.1/metadata")
    app.state.catalog_page_retriever = HTTPPageRetriever()
    response = client.post(
        f"/projects/{project['id']}/candidates/{candidate_id}/normalize",
        json={
            "request_key": "blocked-normalization-0001",
            "expected_catalog_version": 1,
            "expected_project_version": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "blocked"
    assert response.json()["failure_code"] == "blocked_address"
    assert response.json()["project_version"] == 1

    owner["id"] = uuid4()
    hidden = client.get(f"/projects/{project['id']}/products")
    assert hidden.status_code == 404


def test_two_concurrent_exact_normalizations_create_one_observation_and_offer(project_api):
    client, _retriever = _install_fixtures(project_api, [0])
    project, candidate_id = _seed_candidate(project_api, FIXTURES[0]["url"])
    command = {
        "request_key": "parallel-normalization-0001",
        "expected_catalog_version": 1,
        "expected_project_version": 1,
    }

    def send():
        return client.post(
            f"/projects/{project['id']}/candidates/{candidate_id}/normalize", json=command
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: send(), range(2)))
    assert [response.status_code for response in results] == [200, 200]
    assert sorted(response.json()["replayed"] for response in results) == [False, True]
    assert len({response.json()["event_id"] for response in results}) == 1
    with Session(project_api[2]) as session:
        assert session.scalar(select(func.count()).select_from(CatalogObservation)) == 1
        assert session.scalar(select(func.count()).select_from(EntityResolutionEvent)) == 1
        assert session.scalar(select(func.count()).select_from(ProjectProduct)) == 1
        assert session.scalar(select(func.count()).select_from(RetailOffer)) == 1
