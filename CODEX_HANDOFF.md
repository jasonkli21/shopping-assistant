# Codex Handoff

## Objective

Use this repository as the starting point for implementing a personal shopping assistant centered on product search, discovery, evidence-backed research, comparison, and shortlisting. Checkout and transaction processing are explicitly out of scope.

## Current state

- Product design is defined in `docs/product/`.
- Architecture and technology decisions are defined in `docs/architecture/`.
- Detailed Phase 0–9 plans and shared contracts are in [the index](docs/planning/implementation-plans-index.md); `docs/planning/implementation-plan.md` is the roadmap summary.
- The Phase 0 review and small corrections were completed on 2026-10-03. See [validation evidence and unrun checks](VALIDATION.md).
- The API contract is a planning contract, not a promise that all endpoints already exist.
- Code is intentionally limited to Phase 0 scaffolding and a minimal health path.

## Next implementation task

1. Read README, validation, the plans index, the explicitly selected phase plan and predecessor evidence.
2. Reconcile that plan with current code/tests; do not reimplement completed scaffolding.
3. Implement only the selected phase, including migrations, failure handling and UX.
4. Run its acceptance/verification, keeping CI offline and deterministic with provider fakes and real PostgreSQL integration where specified.
5. Update phase status with plan → code → test evidence and explicitly outstanding external checks.
6. Review the completed phase and stop before its successor. Phase 6 requires the documented repository-wide gate.

This supplied directory has no `.git`. Do not invent commit/CI evidence. The Phase 0 source and frontend tests pass; Docker Compose, real-browser connectivity and hosted CI remain externally unverified. No shopping domain feature is present.

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
