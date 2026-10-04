# Phase 3 — Bounded product discovery

Status: planned. Requires Phase 1 project state and Phase 2 task/client contracts. Read the [index](implementation-plans-index.md), AI/search design, Discover UX, testing/observability and API draft. This phase creates candidate observations, not canonical catalog products.

Phase 2 added a shopping-owned `interpret_shopping_intent.v1` task and provider-neutral `PersonalAIClient.generate(AIRequest) -> AIResponse` interface. The deterministic fake is task-aware, but the external client is intentionally unavailable because the checked upstream contract has no verified structured-task route. Phase 3 can add `plan_discovery.v1` under the same boundary and fake pattern; it must not infer that structured live generation is supported or add direct model calls. The Phase 2 conversation supervisor is local and scoped to conversations, not a durable research executor.

## Outcome and scope

A user runs discovery for the apartment vacuum project and sees plausible candidates with search URLs/snippets, the query that found them and clear uncertainty. Offline fixtures exercise the same path as Tavily. Smallest slice: project snapshot → bounded query plan → provider search → persisted candidates → Discover cards and run detail.

Scope: research runs, queries/attempts/results, task-based query generation, Tavily adapter, deterministic fakes, limits, progress/cancellation and discovery UI. Exclude canonical products/variants/offers, deep page research, evidence-backed fit, universal ranking, second live provider, dynamic browser retrieval and distributed jobs. Live discovery acceptance needs an actual credentialed smoke; fixture success alone is insufficient.

## Contracts and persistence

Modules: `research/` owns orchestration/run services/task schemas; `search/` owns neutral search boundary/Tavily/fake; web `features/discovery/`; project services supply bounded context. Maintain explicit dependencies without a general workflow engine.

Add:

- `research_runs`: owner/project, objective (≤2000), type `discovery` initially, status `queued|running|succeeded|partial|failed|canceled|interrupted`, request_key/hash, project revision and immutable input snapshot, configured effective budgets, task/prompt/schema/provider identifiers, queued/started/finished times, counters, sanitized error and summary. Terminal states cannot return to running; rerun creates a new ID. Partial means usable persisted results plus failed/skipped work, not success concealed behind warnings.
- `search_queries`: run FK, ordinal, text, purpose, max_results, state and timestamps. Unique run/ordinal. Persist before calling provider.
- `search_attempts`: query FK, attempt number, provider, status/error/request ID, start/end and result count. Do not count only successes against budgets.
- `search_results`: query/attempt linkage, title/URL/snippet, provider result rank, received_at, provider-neutral metadata. Preserve raw search observations rather than treating them as verified source content.
- `discovery_candidates`: project/run IDs, provisional name/brand/model/category clues, search result references, discovery reason, unverified indicative price text if present, created time and nullable canonical mapping fields introduced in Phase 4. Deduplicate repeated result observations within a run by cautiously normalized URL; do not merge product identities yet. Preserve all result links when grouping duplicates.

Effective limits use the lower of server ceilings and request-selected limits. Existing settings cover queries/candidates/sources; add maximum results per query, total search attempts, deadline and bounded concurrent searches here. Initial discovery is sequential or very low concurrency. A canceled/failed provider attempt consumes its allowance; no automatic retry loops yet beyond an explicit single bounded transport retry for clearly transient failure, with recorded attempts and ceiling. Reserve/check counters before I/O so concurrent work cannot exceed limits.

Query task `plan_discovery.v1`: bounded project snapshot → `{queries:[{text,purpose}], clarification?, explanation}`. Validate query count, nonempty/length, duplicate text, category and budget currency context. Keep exact user constraints; do not broaden must-haves silently. A malformed plan ends safely with a useful message; if AI is unavailable offer an explicitly user-supplied query path with the same run/limits. Snippet-based candidate extraction is a separate validated shopping task or deterministic parsing, labeled provisional. No hallucinated price, identity, source classification or hard fit assertion.

Search adapter honors `SearchQuery.max_results`, timeouts, auth server-side and neutral `SearchResult` shape. Add received/provider metadata only if required and keep fixtures compatible. Record Tavily wire/schema/version contract from actual provider documentation when implementing. Map rate-limit, auth, timeout and malformed payload errors to typed sanitized failures; never leak keys/raw headers. Provider factory defaults to fake, fails clearly for unknown/unconfigured live provider, and cannot fall back silently after live failure.

## API, execution and UX

`POST /projects/{id}/research` accepts objective, type `discovery`, request_key, expected_version and bounded optional budgets; returns 202 run ID. Read list/detail endpoints as drafted. Add `GET /projects/{id}/candidates` for paginated candidate observations; reserve `/products` for Phase 4. Add `POST /projects/{id}/research/{run_id}/cancel`, idempotent and cooperative. Only one active discovery per project initially; return 409 for a different competing command.

Persist command/run first without incrementing project-context revision, then schedule `InProcessResearchExecutor.execute(context, work)` through the application lifespan supervisor. Do not hold a request session or transaction during calls. Each query/result/candidate unit persists atomically; completed results survive another query failure. Cancel checks precede provider calls/persistence; cancellation cannot be undone by a late success. On single-process local restart mark unfinished runs interrupted; do not imply automatic recovery yet. Browser disconnect does not cancel research. Poll run detail for progress and terminal state with backoff; pause polling when hidden/terminal.

Discover shows editable requirement summary and start form, pending/running counters, cancel, candidate list, empty (“no candidates found”), partial/error retry and run history. Cards show provisional identity and original source links with “not yet normalized/researched”; indicative snippet prices remain labeled text with observation time. No canonical offer/assessment badges. Mobile uses a single-column list. Source links are safe http/https outbound URLs, opened with appropriate isolation; never render provider HTML.

## Ordered work packages

1. **Run persistence and lifecycle.** Migrations/models/repositories, immutable context/budget snapshot, scoped commands, transitions and replay. DB tests include duplicate requests, deletion during a run, stale context, counters, cancellation races and rollback.
2. **Provider-neutral search adapter and fixtures.** Extend fake to keyed deterministic responses/errors; add mocked HTTP Tavily contract tests for empty/duplicate/malformed/rate-limited pages and limits. No live calls in normal collection.
3. **Planner and candidate extraction.** Versioned prompts/schemas and eval cases for vacuum/chair/monitor, ambiguity, impossible constraints and irrelevant search noise. Preserve result lineage; prevent unbounded output and unverified “facts.”
4. **Execution and API integration.** In-process scheduling, polling/cancel transport, partial persistence and restart interruption. Tests prove budget ceilings including failures; no hidden retry multiplication.
5. **Discover UX and completion.** Offline full slice, loading/error/empty/mobile/cancel interactions and live smoke instructions. Update API/type generation and schema/observability docs.

Suggested commits follow these five coherent boundaries; combine planner and execution if needed for a working vertical slice rather than shipping disconnected abstractions.

## Acceptance and verification

Fixtures must deterministically create queries, result records and candidates with traceable lineage; never exceed effective queries/attempts/candidates/deadline. Duplicate command replay produces one run. One failing query yields partial if any candidates exist and failed otherwise. Cancel/deletion prevents subsequent mutations. Reload displays completed and interrupted run history. Two URL observations never become a canonical entity in this phase.

Run `make validate`, PostgreSQL migration/research tests, OpenAPI/types check, `uv run pytest tests/evals/discovery` and adapter fixture tests. Manually exercise fake delayed/failed/empty runs and mobile polling. Separately configure Tavily and actual Personal AI (or explicit manual query) and run an opt-in `pytest -m live --run-live` smoke: capture run ID, actual query count, plausible candidate examples and errors/cost metadata. No credentials in fixtures. Without this, mark live outcome externally unverified rather than claiming real discovery passed.

Review: Are budgets enforced before I/O? Is candidate uncertainty honest? Can process/browser failures lose completed work? Does research coordinate modules without leaking vendor types? Does query generation respect currency/must-haves? Can canceled work revive itself?

Handoff: persisted candidates/search lineage, project-version snapshots, run transitions/counters, deterministic provider fixtures and neutral adapter error taxonomy. Phase 4 adds canonical mappings while retaining observations. Phase 5 reuses run semantics for deep research. External gap: Tavily credentials/current API/quotas and live Personal AI query quality. The Phase 2 structured-task external gap remains open until the separate API publishes a verified task-specific contract.
