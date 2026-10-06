# Codex Handoff

## Objective

Use this repository as the starting point for implementing a personal shopping assistant centered on product search, discovery, evidence-backed research, comparison, and shortlisting. Checkout and transaction processing are explicitly out of scope.

## Current state

- Product design is defined in `docs/product/`.
- Architecture and technology decisions are defined in `docs/architecture/`.
- Detailed Phase 0–9 plans and shared contracts are in [the index](docs/planning/implementation-plans-index.md); `docs/planning/implementation-plan.md` is the roadmap summary.
- Phase 0 foundation work is recorded at baseline commit `5ff030d`; Phase 1 persistence, API/types, and UI are in commits `0ff4fd1`, `c0aadc9`, and `6a1e673`. See [Phase 1 acceptance evidence](docs/planning/phase-1-implementation-plan.md) and [validation record](VALIDATION.md).
- Phase 1 implements durable manual projects and requirements. Phase 2 adds durable conversation history and explicitly confirmed intent proposals. Phase 3 adds bounded discovery runs, search lineage, provisional candidates, and the Discover UI. Phase 4 adds guarded catalog normalization, conservative variant mapping, append-only offers and reversible user correction. Phase 5 implements selected-product source snapshots, grounded claims, contextual relations, cited project assessments and inspection UI. Phase 6 adds decisions, private notes, favorites, saved comparison snapshots, workspace routes and explicit assistant proposals. Phase 6's mandatory review gate remains open pending database and browser journey verification (see the [Phase 6 review](docs/planning/phase-6-review.md) and [validation record](VALIDATION.md)). Phases 7 and 8 were implemented locally at the user's explicit direction; neither is accepted, and neither waives an earlier gate.
- Phase 4's independent-review follow-up adds exact-authority conflict handling, source-backed JSON-LD variant extraction, active correction-history replay, retrieval-wide deadlines and bounded decompression, complete offer-pair constraints, paged correction controls and variant-preserving product links. Evidence and remaining external checks are in the [Phase 4 plan](docs/planning/phase-4-implementation-plan.md#independent-review-follow-up--2026-10-04) and [validation record](VALIDATION.md).
- The Phase 3 review follow-up independently enforces provider result/candidate budgets and deadline checks at persistence, sanitizes unknown error codes, adds strict paginated run history and run-scoped candidates, and restores pending discovery forms from validated tab-scoped session storage. Research service behavior is split into command, execution, read and shared-validation modules behind `research.service`; implementation and rerun evidence are in the Phase 3 plan and `VALIDATION.md`.
- Phase 2 is locally validated. Its external Personal AI adapter remains unavailable because the checked upstream contract does not expose structured shopping-task generation; default development uses a deterministic fake. See [Phase 2 acceptance evidence](docs/planning/phase-2-implementation-plan.md), [integration contract note](apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), and [validation record](VALIDATION.md).
- The checkout is a local Git repository on `main`; `git remote -v` returned no configured remote. Hosted CI has not been run.

## Phase 6 status and remaining gate work

Phase 6 implementation is committed locally in coherent feature/documentation slices. The mandatory gate is still open. Its remaining work is: run migration/database checks on a usable PostgreSQL 16 instance; add and run the planned deterministic browser journey suite; manually review desktop/mobile, keyboard focus and cited evidence; and record a live provider/source audit if credentials are available. The user explicitly requested Phase 7 before this gate was closed; that work proceeded without changing the gate status.

Phase 5's prior stop boundary was lifted by the user's explicit Phase 6 request on 2026-10-05. Phase 6 reuses Phase 4 canonical Product → ProductVariant → ProjectProduct identities and Phase 5 source snapshots, claims and immutable cited assessment history. Phase 7 persists ID-based jobs with leases/fencing, bounded mode/source targeting, refresh lineage and append-only offer observations. The user explicitly requested Phases 7 and 8 while prior gates remained open; implementation proceeded without changing their status. PostgreSQL, browser, provider and quality-evaluation checks for Phases 6–8 remain open.

## Phase 7 status and handoff

Migrations `0015`–`0018`, run-ID executor, lifespan recovery, manual runner, retry/cancel APIs and progress/refresh UI are implemented locally. Run a queued or expired job with `cd apps/api && uv run python -m shopping.research.runner --run-id <RESEARCH_RUN_UUID>`. A manual runner does not take over an unexpired lease. The local executor branch is documented as provisional because no representative/worst-case duration or deployment-lifecycle measurements justify remote execution. PostgreSQL migration/concurrency/restart checks, browser journeys and labeled quality/call-count comparisons were not run. Neither Phase 6's gate nor Phase 7 acceptance is closed.

## Phase 8 status and handoff

Migration `0019_explicit_shopping_preferences` and the local profile lifecycle are implemented in commits `98b415b` and `e08e485`. Users can create a pending candidate from a project preference or an explicitly selected rejected-product judgment, then accept/dismiss, edit, revoke/reactivate and apply accepted preferences to another opted-in project. Suggestions are category-scoped, user-applied as editable project requirements, and carry preference ID/revision/scope into assistant and research snapshots. Hard project constraints retain priority. The Personal AI memory contract was checked again: no user-scoped memory read/write/propose/retract API exists, so external memory remains unavailable and no writes occur.

Offline verification passed 164 API tests, 64 frontend tests, API type generation/check, Ruff/format, ESLint, TypeScript and Vite build; offline Alembic SQL reaches migration 0019. PostgreSQL lifecycle/migration/model-drift checks and browser/manual journeys were not run. `TEST_DATABASE_URL` is unset, and local PostgreSQL initialization fails on shared-memory allocation. Phase 8 is not accepted; Phase 6's mandatory gate and Phase 7 acceptance remain open. Read the [Phase 8 implementation record](docs/planning/phase-8-implementation-plan.md) and [validation record](VALIDATION.md). Stop here; Phase 9 has not begun.

The Phase 1–5 features are locally validated. Phase 5 review fixes passed 130 offline API tests, 90 PostgreSQL tests, 33 evidence evals, 53 frontend tests, Ruff/format, generated API type checks, ESLint, TypeScript and production build as recorded in `VALIDATION.md`. Main independently reran the full offline API, PostgreSQL, frontend and type-generation checks before signoff. Hosted CI, live Tavily discovery quality, live retailer-page coverage, external Personal AI structured extraction, live multi-source citation audit, browser/mobile/keyboard inspection of Phase 5 flows, and multi-instance behavior remain unverified. Do not report those checks as passed.

## Non-negotiable boundaries

- Keep the app a modular monolith.
- Keep shopping-domain state in PostgreSQL.
- Keep `personal-ai-system` integration behind `PersonalAIClient`.
- Do not call model providers directly from shopping-domain code.
- Keep search providers behind `SearchProvider`.
- Keep page retrieval behind `PageRetriever`.
- Keep research execution behind `ResearchExecutor`.
- Keep source and test directories separate.
- Avoid infrastructure that is not required by the current phase.
- Preserve inspectability of AI-driven state changes and research evidence.

## Expected implementation order

Follow [the implementation plans index](docs/planning/implementation-plans-index.md). It defines shared ownership/revision/idempotency/provenance contracts and individual Phase 0–9 plans. Complete and review each selected phase before continuing. Phase 6 is the MVP cutoff and repository-wide review gate.

## Luna Max implementation prompt

> Implement only Phase N using `docs/planning/phase-N-implementation-plan.md` and `docs/planning/implementation-plans-index.md`. Read README, handoff, predecessor completion evidence, and referenced product/architecture/API/ADR docs. Reconcile the selected plan against current code/tests; preserve architectural boundaries and implement only that phase. Satisfy its acceptance criteria, run its verification, and update status/docs with plan → code → test evidence and honest outstanding provider/cloud/credentialed checks. Resolve phase review findings, document the successor handoff, and stop. Do not begin Phase N+1. Phase 6 additionally requires the comprehensive repo-wide review gate before Phase 7.
