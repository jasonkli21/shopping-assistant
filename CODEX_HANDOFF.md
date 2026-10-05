# Codex Handoff

## Objective

Use this repository as the starting point for implementing a personal shopping assistant centered on product search, discovery, evidence-backed research, comparison, and shortlisting. Checkout and transaction processing are explicitly out of scope.

## Current state

- Product design is defined in `docs/product/`.
- Architecture and technology decisions are defined in `docs/architecture/`.
- Detailed Phase 0–9 plans and shared contracts are in [the index](docs/planning/implementation-plans-index.md); `docs/planning/implementation-plan.md` is the roadmap summary.
- Phase 0 foundation work is recorded at baseline commit `5ff030d`; Phase 1 persistence, API/types, and UI are in commits `0ff4fd1`, `c0aadc9`, and `6a1e673`. See [Phase 1 acceptance evidence](docs/planning/phase-1-implementation-plan.md) and [validation record](VALIDATION.md).
- Phase 1 implements durable manual projects and requirements. Phase 2 adds durable conversation history and explicitly confirmed intent proposals. Phase 3 adds bounded discovery runs, search lineage, provisional candidates, and the Discover UI. Phase 4 adds guarded catalog normalization, conservative variant mapping, append-only offers and reversible user correction. Phase 5 implements selected-product source snapshots, grounded claims, contextual relations, cited project assessments and inspection UI. Phase 6 adds decisions, private notes, favorites, saved comparison snapshots, workspace routes and explicit assistant proposals. The Phase 6 code is implemented locally; its mandatory review gate remains open pending database and browser journey verification (see the [Phase 6 review](docs/planning/phase-6-review.md) and [validation record](VALIDATION.md)).
- Phase 4's independent-review follow-up adds exact-authority conflict handling, source-backed JSON-LD variant extraction, active correction-history replay, retrieval-wide deadlines and bounded decompression, complete offer-pair constraints, paged correction controls and variant-preserving product links. Evidence and remaining external checks are in the [Phase 4 plan](docs/planning/phase-4-implementation-plan.md#independent-review-follow-up--2026-10-04) and [validation record](VALIDATION.md).
- The Phase 3 review follow-up independently enforces provider result/candidate budgets and deadline checks at persistence, sanitizes unknown error codes, adds strict paginated run history and run-scoped candidates, and restores pending discovery forms from validated tab-scoped session storage. Research service behavior is split into command, execution, read and shared-validation modules behind `research.service`; implementation and rerun evidence are in the Phase 3 plan and `VALIDATION.md`.
- Phase 2 is locally validated. Its external Personal AI adapter remains unavailable because the checked upstream contract does not expose structured shopping-task generation; default development uses a deterministic fake. See [Phase 2 acceptance evidence](docs/planning/phase-2-implementation-plan.md), [integration contract note](apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), and [validation record](VALIDATION.md).
- The checkout is a local Git repository on `main`; `git remote -v` returned no configured remote. Hosted CI has not been run.

## Phase 6 status and remaining gate work

Phase 6 implementation is committed locally in coherent feature/documentation slices. The mandatory gate is still open. The remaining work is limited to this phase: run migration/database tests on a usable PostgreSQL 16 instance; add and run the planned deterministic browser journey suite; manually review desktop/mobile, keyboard focus and cited evidence; and record a live provider/source audit if credentials are available. Update `docs/planning/phase-6-review.md`, the phase plan and `VALIDATION.md` with results. Do not begin Phase 7 until the report explicitly records a passed gate with no unresolved blockers.

Phase 5's prior stop boundary was lifted by the user's explicit Phase 6 request on 2026-10-05. Phase 6 reuses Phase 4 canonical Product → ProductVariant → ProjectProduct identities, timestamped offers, observations and the existing bounded `PageRetriever`, plus Phase 5 `SourceSnapshot` and claim IDs, frozen freshness defaults and immutable cited assessment history. Phase 4 corrections remain reversible audited user judgments and refresh never moves offers. The Phase 3/5 research supervisor is local single-process execution, and Phase 9 must revisit lifetime/recovery before multi-instance hosting. Do not start Phase 7 unless the Phase 6 gate is recorded as passed.

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
