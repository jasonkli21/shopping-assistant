# Codex Handoff

## Objective

Use this repository as the starting point for implementing a personal shopping assistant centered on product search, discovery, evidence-backed research, comparison, and shortlisting. Checkout and transaction processing are explicitly out of scope.

## Current state

- Product design is defined in `docs/product/`.
- Architecture and technology decisions are defined in `docs/architecture/`.
- Detailed Phase 0–9 plans and shared contracts are in [the index](docs/planning/implementation-plans-index.md); `docs/planning/implementation-plan.md` is the roadmap summary.
- Phase 0 foundation work is recorded at baseline commit `5ff030d`; Phase 1 persistence, API/types, and UI are in commits `0ff4fd1`, `c0aadc9`, and `6a1e673`. See [Phase 1 acceptance evidence](docs/planning/phase-1-implementation-plan.md) and [validation record](VALIDATION.md).
- Phase 1 implements durable manual projects and requirements. Phase 2 adds durable conversation history and explicitly confirmed intent proposals. Phase 3 adds bounded discovery runs, search lineage, provisional candidates, and the Discover UI. Phase 4 adds guarded catalog normalization, conservative variant mapping, append-only offers and reversible user correction. Phase 5 locally implements selected-product source snapshots, grounded claims, contextual relations, cited project assessments and inspection UI; independent review remains pending. Phases 6–9 remain planned.
- Phase 4's independent-review follow-up adds exact-authority conflict handling, source-backed JSON-LD variant extraction, active correction-history replay, retrieval-wide deadlines and bounded decompression, complete offer-pair constraints, paged correction controls and variant-preserving product links. Evidence and remaining external checks are in the [Phase 4 plan](docs/planning/phase-4-implementation-plan.md#independent-review-follow-up--2026-10-04) and [validation record](VALIDATION.md).
- The Phase 3 review follow-up independently enforces provider result/candidate budgets and deadline checks at persistence, sanitizes unknown error codes, adds strict paginated run history and run-scoped candidates, and restores pending discovery forms from validated tab-scoped session storage. Research service behavior is split into command, execution, read and shared-validation modules behind `research.service`; implementation and rerun evidence are in the Phase 3 plan and `VALIDATION.md`.
- Phase 2 is locally validated. Its external Personal AI adapter remains unavailable because the checked upstream contract does not expose structured shopping-task generation; default development uses a deterministic fake. See [Phase 2 acceptance evidence](docs/planning/phase-2-implementation-plan.md), [integration contract note](apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), and [validation record](VALIDATION.md).
- The checkout is a local Git repository on `main`; `git remote -v` returned no configured remote. Hosted CI has not been run.

## Next implementation task

1. Read README, validation, the plans index, the explicitly selected phase plan and predecessor evidence.
2. Reconcile that plan with current code/tests; do not reimplement completed scaffolding.
3. Implement only the selected phase, including migrations, failure handling and UX.
4. Run its acceptance/verification, keeping CI offline and deterministic with provider fakes and real PostgreSQL integration where specified.
5. Update phase status with plan → code → test evidence and explicitly outstanding external checks.
6. Review the completed phase and stop before its successor. Phase 6 requires the documented repository-wide gate.

The next action is independent main-session review of Phase 5 and resolution of any findings. Stop before Phase 6. Phase 5 reuses Phase 4 canonical Product → ProductVariant → ProjectProduct identities, timestamped offers, observations and the existing bounded `PageRetriever`. Its `SourceSnapshot` and claim IDs, frozen freshness defaults and immutable cited assessment history are the successor contracts for Phase 6 comparison. Phase 4 corrections remain reversible audited user judgments and refresh never moves offers. The Phase 3/5 research supervisor is local single-process execution, and Phase 9 must revisit lifetime/recovery before multi-instance hosting.

The Phase 1–4 features and Phase 4 independent-review fixes are locally validated. Phase 5 local implementation passed PostgreSQL integration, deterministic grounding evals, generated API types and frontend checks recorded in `VALIDATION.md`; its independent review remains. Hosted CI, live Tavily discovery quality, live retailer-page coverage, external Personal AI structured extraction, live multi-source citation audit, browser/mobile inspection of Phase 5 flows, multi-instance behavior, and full keyboard-only traversal remain unverified. Do not report those checks as passed.

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
