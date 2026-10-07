# API Contract

`GET /health`, feature APIs through Phase 8, and the local Phase 9 auth/readiness/export/purge foundation are implemented. Cloud behavior remains unverified. OpenAPI is the source for committed TypeScript transport types in `packages/api-types/src/index.ts`; regenerate with `make api-types` and verify with `make api-types-check`. Phase acceptance and open gates are tracked in [`../current-state.md`](../current-state.md); this document describes the transport contract, not phase status. See the [plans index](../planning/implementation-plans-index.md) and [validation record](../../VALIDATION.md) for related contracts and evidence.

## Shared conventions

- Transport schemas are distinct from ORM models. Opaque UUID IDs, UTC ISO-8601 timestamps and decimal-string money with explicit currency; unknown values stay null/unknown.
- Private resources are scoped to a stable server-side owner from Phase 1. Locally, `LOCAL_OWNER_ID` selects that principal (with a fixed development default); no client can set `owner_id`. Staging/production require a verified Firebase ID token, an exact configured UID allowlist, and the one-time `firebase_owner_bindings` mapping. The client sends short-lived bearer tokens in `Authorization`, including on fetch-based SSE; tokens never go in query strings. Unconfigured or foreign UIDs cannot select another owner.
- Context mutations carry `expected_version`, return the committed project revision and conflict with 409. Nested references must belong to the same owner/project. Catalog/profile/comparison revisions are explicit where relevant.
- Conversation/research commands carry `request_key`: exact replay returns the same command result; same key/different payload returns 409. Validated AI proposals apply atomically and explicitly; prose/deltas cannot mutate durable state.
- Error envelope `{error:{code,message,details?,request_id?}}`; field validation 422, unavailable/foreign-owner ID 404, revision/transition conflict 409. Sanitize provider errors. Bounded cursor pagination is specified in the index.
- Project context edits advance its revision. Activity bookkeeping (message/run status, query/source observations and stream subscriptions) does not advance it; snapshot/run revisions describe the input used. Derived comparisons must record the committed context revision when created by a context mutation.

## System — Phase 0; readiness foundation — Phase 9

Implemented locally: `GET /health` is liveness and does not query PostgreSQL. `GET /ready` checks database reachability, the current Alembic head, and (when Firebase auth is enabled) the configured owner binding. Failures return a generic 503 without secret details. No hosted check has run.

```text
GET /health
GET /ready
```

## Projects and requirements — Phase 1

Implemented against PostgreSQL. `POST /projects` returns 201 and a full project; list returns summaries and `next_cursor`; detail returns the project with requirements sorted by position. Project PATCH carries `expected_version` in its body. Requirement create carries it as a query parameter, while requirement PATCH carries it in the body. Project and requirement deletion carry it as a query parameter and return 204 for project tombstones or the updated project for requirement removal. Omitted PATCH fields stay unchanged; explicit `null` clears nullable fields. Money is transported as decimal strings with an explicit supported currency.

```text
POST   /projects
GET    /projects
GET    /projects/{project_id}
PATCH  /projects/{project_id}
DELETE /projects/{project_id}
GET    /projects/{project_id}/requirements
POST   /projects/{project_id}/requirements
PATCH  /projects/{project_id}/requirements/{requirement_id}
DELETE /projects/{project_id}/requirements/{requirement_id}
```

DELETE tombstones/hides; archive is a reversible status. Every private read and write checks the local server-side owner. Mutations lock and validate the project revision, commit once, and return 409 with the current revision when stale. List pagination uses a bounded limit (default 20, max 100), opaque cursors and deterministic update-time/ID ordering. Inputs reject unknown fields. Errors use `{error:{code,message,details?,request_id?}}`; malformed requests are 422, missing or foreign-owner resources 404, stale revisions 409, and unexpected failures are sanitized. No product/research feature is implied.

## Conversations and proposals — Phase 2

```text
GET  /projects/{project_id}/conversations
GET  /projects/{project_id}/messages
POST /projects/{project_id}/messages
GET  /projects/{project_id}/messages/stream?message_id=...
POST /projects/{project_id}/proposals/{proposal_id}/apply
POST /projects/{project_id}/proposals/{proposal_id}/dismiss
```

POST accepts `text`, `request_key`, and `expected_version`; it saves the user message and assistant placeholder before returning 202 with durable IDs. Exact command replay is checked before revision validation and includes both text and version; a changed payload with the same key returns 409. The page API uses ordered ordinal cursors and is the history source of truth.

The local Phase 2 stream attaches to one existing generation, with snapshot/delta/proposal/complete/error events and heartbeats. Reconnect cannot create another command. Token-level replay is not guaranteed; persisted history/snapshot is authoritative. Assistant output and its validated proposal persist together. A `conversation_busy` 409 or `generation_capacity` 503 is returned before saving the new command, so the client can restore its text and retry with a fresh request key; an uncertain network acknowledgment retains the original key for exact replay.

Applying all proposal operations runs through the Phase 1 project service in one transaction and increments project revision once. Applied replay returns its saved project result and UTC `applied_at` even after later edits while the project remains active. Apply and dismiss first check the live owner-scoped project; foreign or tombstoned projects return 404 before an applied replay can return its saved snapshot. Dismissal is replay-safe while the project remains active.

Generation is local single-process work owned by application lifespan. The supervisor uses its own short-lived database sessions on worker threads, keeps provider I/O outside database transactions, and waits for owned database writes during shutdown. It also has bounded concurrency and timeout; a disconnected stream detaches, and restart recovery marks unfinished work interrupted. The task output is bounded JSON, stored prompt snapshots are cleared at terminal state, and only Phase 1-valid proposals can change project context. The current external Personal AI contract has ordinary chat streaming but does not define the task-specific structured generation envelope, so external mode reports `provider_unavailable`; local mode uses deterministic fake responses. The assistant SSE stream must therefore not be represented as upstream provider token streaming. Phase 9 must verify/adapt execution lifetime and authenticated fetch streaming for deployed multi-instance/request lifecycle; such an adaptation must preserve command/proposal idempotency.

## Discovery/research — Phase 3, extended in Phases 5/7

```text
POST /projects/{project_id}/research
GET  /projects/{project_id}/research
GET  /projects/{project_id}/research/{research_run_id}
POST /projects/{project_id}/research/{research_run_id}/cancel
GET  /projects/{project_id}/candidates
```

Research is a bounded command, with objective/type/request_key/expected_version and server-capped optional limits; POST returns 202 and run ID. Phase 3 type is discovery; Phase 5 adds selected-product research; Phase 7 adds mode/refresh/source targets/jobs. Candidate observations are not canonical products, offers or evidence. Progress initially polls durable run state.

`POST /research` accepts optional `budgets` fields `max_queries`, `max_candidates`, `max_results`, `max_results_per_query`, `max_attempts`, `deadline_seconds`, and `max_concurrent`; each value can only lower its server cap. An optional `manual_queries` list bypasses only AI query planning. It does not bypass ownership, revision, idempotency, budget, or timeout checks. `GET /research` accepts a bounded limit; candidate paging uses `limit` and an opaque `cursor`.

At run creation, the API snapshots the project and requirement set at `snapshot_revision` and persists the command before returning. Research activity never increments project revision. A query and attempt are committed before provider I/O; each query's results, candidates, and candidate-to-result references commit atomically. Duplicate safe URLs are grouped within that run while retaining every result reference. Candidate fields are provisional clues only; no canonical identity, normalized price, source classification, or fit score is asserted. `SearchAttemptRead.usage_units` is nullable provider-reported usage, not currency.

Runs are `queued|running|succeeded|partial|failed|canceled|interrupted`. Partial means there is at least one persisted candidate plus failed/skipped planned work. Empty successful search and explicit clarification are both terminal success with a useful summary. Cancellation is repeatable and late provider results cannot revive a terminal run. Deleted projects hide all project resources and interrupt active runs. The lifespan-owned runner uses an in-process executor; startup marks unfinished runs interrupted, and multi-instance deployment is not supported by this execution model.

Exact request replay is checked before the project revision; a matching body returns the original run, while a changed body with the same key conflicts. The run snapshots project requirements/revision without changing that revision. Optional query/candidate/result/result-per-query/attempt/deadline/concurrency budgets are capped by server settings. Manual queries skip the unavailable Personal AI planner but use the same snapshots and budgets. Different concurrent runs for a project conflict. Queries and attempts persist before provider I/O; result/candidate lineage commits per query. Failed or skipped work yields `partial` when candidates were saved, otherwise `failed` unless all work completed successfully or the planner asks for clarification. Cancellation is idempotent; project deletion and single-process restart interrupt unfinished runs, and terminal runs cannot accept late writes.

The local lifespan-owned supervisor uses the existing `ResearchExecutor` boundary, distinct from conversation generation, and synchronous database operations run in worker threads with short-lived sessions. It is deliberately single-process local execution, not a distributed job system. Search defaults to the deterministic fake; Tavily is an opt-in adapter documented in [the search contract](../architecture/search-provider-contract.md). Current live Tavily credentials and live Personal AI structured planning are not verified.

## Catalog and normalization — Phase 4

```text
POST /projects/{project_id}/candidates/{candidate_id}/normalize
POST /projects/{project_id}/candidates/{candidate_id}/correction
POST /projects/{project_id}/candidates/{candidate_id}/correction/revert
GET  /projects/{project_id}/products
GET  /products?q=...&limit=...&cursor=...
GET  /products/{product_id}
GET  /products/{product_id}/offers?variant_id=...
```

Catalog reads and writes use the server-side owner. `GET /products` searches that owner's variants and supplies existing-variant choices for correction. Product detail returns variants, identifier namespaces, bounded attributes and origin metadata; offer history is variant-specific and paginated by `limit` (default 20, max 100) and opaque `cursor`. Project product pages return `catalog_version` and `project_version` snapshots.

`POST .../normalize` accepts `request_key`, `expected_catalog_version`, and `expected_project_version`. Retrieval and extraction happen before the short write transaction. The transaction rechecks both versions, writes the immutable page observation and resolution event, and advances the project version only when it adds a project-to-variant link. A matching replay returns the saved event before version checks or page retrieval; reusing a key for a different body, candidate, or command conflicts with 409. Retrieval/extraction outcomes return typed `auto_linked|unresolved|failed|blocked|unsupported` results so an unavailable page leaves the candidate usable.

`POST .../correction` accepts the same request/version fields, a required explanation, and exactly one target: an existing `target_variant_id`, a `new_variant` under an owner-owned product, or a `new_product` with one explicitly named variant. `POST .../correction/revert` restores the previous mapping for the latest active manual assignment. Both commands are replay-safe and audited. Corrections do not move offers; each offer remains attached to the variant observed on its source page. Refreshes preserve manual mappings, while observations, event history and offers remain inspectable.

Canonical identity is Product → ProductVariant → timestamped RetailOffer. Resolution uses matching namespaced identifiers or an exact brand/model family plus a complete compatible set of known variant dimensions. Partial or unknown variant dimensions do not select a richer known variant; title and URL similarity never merge products. Offers preserve amount as decimal text, currency, availability, condition, retailer URL and observation time. Unknown money stays unknown, and outbound links are limited to credential-free HTTP(S). Candidate reads include the latest normalization status and correction revertibility.

The single `PageRetriever` enforces public destination checks and IP-pinned connections per redirect, with bounded time, redirects, decoded bytes and supported content types. Extraction strips executable page text from visible excerpts, accepts only exact page-backed excerpts and does not process page instructions. The local structured-data extractor supports one Product object and returns unsupported for ambiguous or absent product data. No external Personal AI extraction endpoint is assumed; that structured-task integration remains unavailable pending a verified upstream contract.

## Evidence — Phase 5

```text
GET /products/{product_id}/sources?variant_id=...
GET /projects/{project_id}/products/{project_product_id}/research
GET /projects/{project_id}/claims/{claim_id}
GET /projects/{project_id}/sources/{snapshot_id}
```

`POST /projects/{project_id}/research` accepts `type: product_research` with one to three selected ProjectProduct IDs and server-capped source, page, byte, AI-call and deadline budgets. The run snapshots project requirements and exact catalog/variant revisions. Run detail exposes target and stage progress; project-product research reads expose source attempts, validated claims and immutable assessment history. Source-backed claims expose exact excerpt, locator, qualifiers, source classification, content hash, publication/retrieval times and context-aware relations. Assessments cite claim IDs or report unknown, and current revision comparisons mark old assessments stale without changing their history. Failed or blocked attempts remain visible. All project-relative reads enforce owner and selected-product membership; raw arbitrary HTML is never an API-rendered evidence view. Local deterministic task fixtures exercise the contract; live structured Personal AI output and source quality remain unverified.

## Decisions and comparisons — Phase 6

```text
GET    /projects/{project_id}/shortlist
GET    /projects/{project_id}/rejections
GET    /projects/{project_id}/products/{project_product_id}/decision
POST   /projects/{project_id}/shortlist/{project_product_id}
DELETE /projects/{project_id}/shortlist/{project_product_id}
POST   /projects/{project_id}/rejections/{project_product_id}
DELETE /projects/{project_id}/rejections/{project_product_id}
POST   /projects/{project_id}/products/{project_product_id}/purchased
DELETE /projects/{project_id}/products/{project_product_id}/purchased
GET    /projects/{project_id}/notes
PUT    /projects/{project_id}/notes
DELETE /projects/{project_id}/notes
GET    /projects/{project_id}/products/{project_product_id}/notes
PUT    /projects/{project_id}/products/{project_product_id}/notes
DELETE /projects/{project_id}/products/{project_product_id}/notes
POST   /projects/{project_id}/comparisons
GET    /projects/{project_id}/comparisons
GET    /projects/{project_id}/comparisons/{comparison_id}
PATCH  /projects/{project_id}/comparisons/{comparison_id}
POST   /projects/{project_id}/comparisons/{comparison_id}/regenerate
DELETE /projects/{project_id}/comparisons/{comparison_id}
GET    /saved-products
GET    /saved-products/{variant_id}
PUT    /saved-products/{variant_id}/favorite
DELETE /saved-products/{variant_id}/favorite
```

Use exact ProjectProduct IDs, not family-level product IDs, for project decisions and comparison membership. Decision commands carry `expected_version` and an idempotency `request_key`; notes and comparison edits use project revisions, while comparison edits also carry `expected_comparison_version`. Favorites are owner/variant scoped and use their own version without changing a project revision. Purchased is a reversible manual judgment. One current decision state prevents simultaneous shortlist/rejection.

Comparisons persist ordered variants, dimensions and immutable generated snapshots. Facts, offers, cited evidence, project-fit assessments and user notes retain cell provenance; unknown, conflicting, stale and incomparable cells remain visible in differences mode. Only demonstrably equal known values are hidden. Supported units normalize deterministically; unequal currencies are not ranked. `GET` does not regenerate a snapshot; use the explicit `/regenerate` command with both expected versions. These local routes and schemas are generated into the committed API types.

## Profiles/memory and account privacy — Phases 8/9

The Phase 8 contract covers owner-scoped profile/preferences/candidates, promotion/revocation, and conditional external memory operations with explicit consent. No external memory API is assumed to exist. Local Phase 9 endpoints are:

```text
GET    /account/export
DELETE /account/data?confirm=DELETE_MY_DATA
```

Export is owner-scoped, versioned JSON, bounded at 2,000 rows/10 MiB, excludes full retrieved page text and identity bindings, and redacts URL credentials. Purge requires the exact confirmation query, removes owner application rows and the Firebase UID binding, and retains a timestamp/count-only audit row. The owner must be rebound before private access resumes. PostgreSQL authorization, export/purge, migration, and restore checks remain open; do not treat this local contract as security verification.
