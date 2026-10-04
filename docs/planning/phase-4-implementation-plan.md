# Phase 4 — Product, variant and offer normalization

Status: planned. Requires Phase 3 candidates/search lineage and run lifecycle. Read the [index](implementation-plans-index.md), data model, evidence model, AI/search design and ADR 0002. Canonical does not mean all claims are unquestionably true.

## Outcome and scope

Two retailer URLs for the same vacuum resolve to one product and the correct variant, with two timestamped offers. A different battery/accessory bundle stays a distinct variant. Ambiguous matches remain separate/reviewable, and the user can correct a mistaken link without losing provenance.

Scope: relational catalog, bounded category JSONB, identity/offer extraction, conservative entity resolution, candidate mapping, product detail basics and manual correction. Exclude multi-source research synthesis, broad ontology, fuzzy automatic merges without evidence, vector matching, cross-currency totals, historical price alerts, ownership lifecycle and browser automation. Phase 5 adds detailed claims/research; this phase supplies enough retrieval for canonical identity/offers only.

## Domain, database and API contracts

Catalog owns `Product`, `ProductVariant`, `RetailOffer`, identity aliases and candidate mappings. Research invokes catalog services; retrieval remains in `extraction/`. Keep a simple brand string/normalized key; a separate Brand table is unnecessary until actual query/use warrants it.

Tables:

- `products`: owner scope for this personal catalog, UUID, canonical name, brand, category, optional model family, timestamps, revision. No price/fit/shortlist columns.
- `product_variants`: product FK, display name, explicit identity attributes/identifiers, bounded JSONB category attributes, revision and timestamps. A product with no known variation has one explicit “unspecified” variant, not an imaginary specification. Unknown variant and confirmed exact SKU are distinct.
- `product_identifiers`: variant/product reference, scheme (`manufacturer_model|gtin|mpn|retailer_sku`), value and namespace/source observation reference. Retailer SKU is scoped to retailer; model keys scoped to brand/category. Only enforce uniqueness where semantics actually guarantee identity; conflicting identifiers create review issues, not forced merges.
- `project_products`: project/variant FK, unique pair, first-discovered candidate/run references, discovery reason and timestamps. Retain a product association through variant.parent. Project-local judgments remain future decision state. Aggregate cards may group variants but decisions reference exact ProjectProduct.
- `retail_offers`: variant, retailer name/domain, URL, decimal amount/currency or explicitly unknown price, availability `in_stock|out_of_stock|preorder|unknown`, condition, observed_at, extraction observation reference. Append observations; identical observation retries use a unique observation key. Do not unique all offers by URL or overwrite history. No cross-currency cheapest label. Availability/price fetched at a time are not purchase guarantees.
- `catalog_observations`: candidate/run, requested/final URL, retrieved_at, content hash, extractor/task versions, validated identity/attribute/offer extraction, small supporting excerpts and warnings. These are extraction provenance; Phase 5 will link them to richer SourceSnapshot records without discarding them.
- `entity_resolution_events`: observations/candidate, proposed/selected variant, reason/identifier evidence, auto/manual/unresolved status, actor/time and reversible mapping history. No hidden identity merges.

Category attributes use a flat bounded map of attribute keys to typed value/unit/origin/observation references; avoid storing a whole model response. Existing JSONB attribute fields can hold this; do not add a duplicate `product_attributes` EAV table without a concrete need. A promoted canonical value requires deterministic normalization and provenance; tentative marketing statements remain observations. User corrections have origin `user_correction` and do not rewrite the source.

Add Phase 3 candidate nullable mapping to ProjectProduct/variant and migrated existing candidates unchanged/unresolved. All reads are owner-scoped; no unrelated project notes in global product responses. Catalog writes use `expected_catalog_version`; project linking also uses expected project version. Short transactions validate FK/ownership and apply links/offers/audit together. Remote retrieval/extraction is outside them. Concurrent identifier collisions re-read existing candidates and retry the small deterministic transaction, not provider calls.

API: `GET /projects/{id}/products`, `GET /products/{id}`, `GET /products/{id}/offers?variant_id=...`, `POST /projects/{id}/candidates/{candidate_id}/normalize` (request_key/version), and explicit scoped catalog correction/link commands. Candidate endpoints remain available. Normalization can be a run type with target candidate IDs; responses expose unresolved status. Provide manual assign/reassign to existing/new variant; do not implement a universal merge/split graph editor. Reassignment is reversible from events and leaves original observations/history intact.

## Retrieval and extraction safety

Implement one HTTPX `PageRetriever` in `extraction/`: bounded timeout/redirects/decoded bytes/content types, UTC retrieval time, requested and final URL and content hash. HTTP/S only. Reject credentials-in-URL, loopback/private/link-local/multicast IPs and cloud metadata; validate resolved addresses and every redirect, prevent DNS rebinding by pinning/validating connected destination, and test this offline. If the transport cannot enforce that, restrict to explicit public host allowlists until it can; superficial URL parsing alone is insufficient. Do not fetch arbitrary user/provider URLs without these guards.

HTML-to-text strips scripts/styles and preserves compact relevant text. Unsupported content, blocked pages, oversized payloads and timeouts return typed failures. No executing JavaScript or accepting instructions from pages. A versioned shopping extraction task returns identifiers, variant distinguishing fields, typed attributes and offer observations with supporting text/locators. Reject invented source text, incompatible currency/units, impossible dimensions, malformed amounts and unrelated page products. No LLM entity merge decision alone.

Entity resolution order: normalized authoritative identifier in matching namespace → matching brand/model plus compatible known variant dimensions → unresolved suggestions for manual review. Name similarity only suggests. Bundle, region, color, capacity, generation and condition must not be silently collapsed. URL tracking normalization preserves variant/query semantics; redirects do not establish identity by themselves.

## Ordered work packages

### 4A — Catalog persistence and migration

Implement models/services, migration, bounded attribute schema, decimal/offer constraints and candidate mapping. Import models for Alembic. DB tests cover reused variant links, multiple offers/currencies/times, conflicting identifiers, concurrent normalization and no lost search lineage. Preserve Phase 3 candidates during upgrade; downgrade limits/data loss documented.

### 4B — Retrieval and identity/offer extraction

Add HTTP adapter with mocked transport/security tests and recorded manufacturer/retailer fixture pages (minimal excerpts, no credentials). Extend fake documents with metadata compatibly. Create task-shaped AI fixtures and extraction evals: vacuum kit versus body, monitor size/region, chair dimensions/units, sale versus crossed-out price, unavailable currency and multi-product page. Extraction must return unknown/warnings rather than invented fields.

### 4C — Resolution and manual correction slice

Implement deterministic matcher, unresolved queue/state and assign/reassign commands. Persist match evidence and idempotent observation keys. Never auto-merge on title/URL. Validate correction payloads and stale revisions; reassign ProjectProduct links without changing offers to a different variant implicitly. Moved offers need explicit observation-backed correction and audit. Test wrong-match recovery and replay.

### 4D — Catalog UX and handoff

Discover cards transition from provisional to normalized; show unresolved choices. Detail shows identity, chosen variant, structured attributes with origin, offer time/currency/condition and safe outbound links. Manual correction is clearly a user edit; unknown/blocked retrieval keeps the candidate usable. Include pending/failed/retry/empty-offer states, stale revision handling and mobile variant controls.

Suggested commits: schema/mapping; retrieval/extraction fixtures; matching/corrections; API/types/UI; review evidence.

## Acceptance and verification

Fixture pairs of same SKU map correctly; variant/bundle/region conflicts stay distinct or unresolved. Repeated normalization never duplicates ProjectProduct or one offer observation. Prices exist only on timestamped offers. Manual reassign is inspectable/reversible and preserves source/search lineage. Unsupported pages cannot produce fabricated normalized facts. SSRF/redirect/size limits pass mocked tests. Prior Phase 3 runs/candidates remain readable after migration.

Run `make validate`, PostgreSQL catalog/mapping/migration tests, OpenAPI/types check and `uv run pytest tests/evals/normalization`. Add targeted extraction security/fixture tests to default CI. Run migration upgrade from a Phase 3 seeded disposable DB, `alembic check`, and correction rollback tests. Separately inspect a few actual manufacturer/retailer pages with opt-in live tests; document access failures. Do not claim universal retailer coverage.

Review: Are variant discriminators preserved? Does an unknown value stay unknown? Can manually corrected identity be refreshed without overwriting the correction? Are facts versus observed marketing claims still distinguishable? Is there only one retriever? Are per-owner catalog boundaries ready for auth?

Handoff: canonical IDs, exact ProjectProduct/variant references, offer history, observation/identifier provenance, reversible resolution events and bounded retriever. Phase 5 expands SourceSnapshot/claim provenance and assessments around these contracts. External gaps: live page coverage and verified Personal AI extraction contract/quality; browser fallback remains deferred.
