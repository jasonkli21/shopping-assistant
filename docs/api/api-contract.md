# API Contract (Phases 0–2 Implemented; Later Phases Planned)

`GET /health`, the Phase 1 project/requirement API, and the Phase 2 conversation/proposal API are implemented. Phase 3 onward remains a planning contract; the [plans index](../planning/implementation-plans-index.md) and selected phase plans define those future commands. OpenAPI is the source for committed TypeScript transport types in `packages/api-types/src/index.ts`; regenerate with `make api-types` and verify with `make api-types-check`.

## Shared conventions

- Transport schemas are distinct from ORM models. Opaque UUID IDs, UTC ISO-8601 timestamps and decimal-string money with explicit currency; unknown values stay null/unknown.
- Private resources are scoped to a stable server-side owner from Phase 1. Locally, `LOCAL_OWNER_ID` selects that principal (with a fixed development default); no client can set `owner_id`. Firebase auth/allowlisted identity mapping arrives before cloud exposure in Phase 9.
- Context mutations carry `expected_version`, return the committed project revision and conflict with 409. Nested references must belong to the same owner/project. Catalog/profile/comparison revisions are explicit where relevant.
- Conversation/research commands carry `request_key`: exact replay returns the same command result; same key/different payload returns 409. Validated AI proposals apply atomically and explicitly; prose/deltas cannot mutate durable state.
- Error envelope `{error:{code,message,details?,request_id?}}`; field validation 422, unavailable/foreign-owner ID 404, revision/transition conflict 409. Sanitize provider errors. Bounded cursor pagination is specified in the index.
- Project context edits advance its revision. Activity bookkeeping (message/run status, query/source observations and stream subscriptions) does not advance it; snapshot/run revisions describe the input used. Derived comparisons must record the committed context revision when created by a context mutation.

## System — Phase 0; readiness in Phase 9

Implemented: `GET /health` is liveness and does not query PostgreSQL. Database/schema readiness arrives in Phase 9.

```text
GET /health
GET /ready       # Phase 9, bounded DB/schema readiness
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

## Catalog and normalization — Phase 4

```text
POST /projects/{project_id}/candidates/{candidate_id}/normalize
GET  /projects/{project_id}/products
GET  /products/{product_id}
GET  /products/{product_id}/offers?variant_id=...
```

Normalization/link/correction commands are owner/version scoped and defined precisely in Phase 4 OpenAPI. Canonical identity is Product → ProductVariant → timestamped RetailOffer. ProjectProduct links an exact variant; corrections retain provenance and history. A URL is not product identity.

## Evidence — Phase 5

```text
GET /products/{product_id}/sources?variant_id=...
GET /projects/{project_id}/products/{project_product_id}/research
GET /projects/{project_id}/claims/{claim_id}
```

Add scoped source-snapshot inspection routes with the implementation contract. Source-backed claims expose exact excerpt/context/content-version provenance; assessments cite claim IDs and project context. Raw arbitrary HTML is never an API-rendered evidence view.

## Decisions and comparisons — Phase 6

```text
GET    /projects/{project_id}/shortlist
POST   /projects/{project_id}/shortlist
DELETE /projects/{project_id}/shortlist/{project_product_id}
POST   /projects/{project_id}/rejections
DELETE /projects/{project_id}/rejections/{project_product_id}
POST   /projects/{project_id}/comparisons
GET    /projects/{project_id}/comparisons
GET    /projects/{project_id}/comparisons/{comparison_id}
PATCH  /projects/{project_id}/comparisons/{comparison_id}
DELETE /projects/{project_id}/comparisons/{comparison_id}
```

Use exact ProjectProduct IDs, not family-level product IDs, for decisions/comparison membership. Notes, favorites and manual purchased/undo commands are added by the Phase 6 plan. One current decision state prevents simultaneous shortlist/rejection. Comparisons persist dimensions/provenance and expose unknown/conflict/stale cells; saved snapshots do not silently regenerate.

## Profiles/memory and production — Phases 8/9

Phase 8 adds owner-scoped profile/preferences/candidates, promotion/revocation and conditional external memory operation contracts, with explicit consent. No external memory API is assumed to exist. Phase 9 adds Firebase token verification/authorization and owner export/purge plus readiness. Final routes/types must be documented and authorization-tested across the entire implemented route inventory before release.
