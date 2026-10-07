# Documentation guide

This page routes documentation by task. For any disagreement, use this authority order:

1. Code, executable schemas/contracts, migrations, and tests describe delivered behavior.
2. Release, review, and verification records show what was exercised and verified.
3. Accepted ADRs record durable decisions and supersession.
4. Product and architecture documents describe intended scope and boundaries.
5. Active plans describe authorized future work and sequencing; they do not prove delivery.
6. Historical or superseded documents provide context only.

Security and privacy constraints take precedence. A current user instruction can authorize work beyond the active plan without changing earlier acceptance evidence.

## Document classes

- [`current-state.md`](current-state.md) is the only living implementation-status summary.
- [`adr/`](adr/) contains durable decisions.
- [`planning/`](planning/) contains the phase index, plans, and review handoffs. A plan is not evidence that code exists; review handoffs record findings, and any embedded follow-up prompt does not authorize work or change acceptance.
- [`../VALIDATION.md`](../VALIDATION.md) is chronological verification evidence, not required fresh-session reading. Its latest entry records the 2026-10-07 Phase 9 review corrections and remaining offline/PostgreSQL failures; earlier implementation baselines and open Phase 6–8 gates remain recorded below it.
- `history/` is reserved for superseded material worth retaining outside Git history. The old handoff and coordinator diary are retained only as short redirects; their prior text remains in Git history.

## Route by task

| Task | Start here |
|---|---|
| Product scope and requirements | [`product/product-vision.md`](product/product-vision.md), [`product/ux-design.md`](product/ux-design.md), and the [roadmap](product/roadmap.md) |
| API contracts and generated types | [`api/api-contract.md`](api/api-contract.md), [`packages/api-types/README.md`](../packages/api-types/README.md), and `scripts/generate_api_types.py` |
| Persistence, data model, and migrations | [`architecture/data-model.md`](architecture/data-model.md), [ADR 0002](adr/0002-postgres-domain-store.md), `apps/api/migrations/`, and `apps/api/tests/db/` |
| Discovery and research execution/jobs/recovery | [`apps/api/src/shopping/research/README.md`](../apps/api/src/shopping/research/README.md), [`architecture/research-execution-decision.md`](architecture/research-execution-decision.md), and the [Phase 7 plan](planning/phase-7-implementation-plan.md) |
| Product normalization and offers | [`apps/api/src/shopping/catalog/README.md`](../apps/api/src/shopping/catalog/README.md), [`architecture/data-model.md`](architecture/data-model.md), and [`architecture/research-evidence.md`](architecture/research-evidence.md) |
| Evidence, claims, and assessment | [`apps/api/src/shopping/evidence/README.md`](../apps/api/src/shopping/evidence/README.md), [`architecture/research-evidence.md`](architecture/research-evidence.md), and [ADR 0004](adr/0004-evidence-first-research.md) |
| Decisions, comparisons, and project workspace | [`apps/api/src/shopping/projects/README.md`](../apps/api/src/shopping/projects/README.md), [`apps/api/src/shopping/comparisons/README.md`](../apps/api/src/shopping/comparisons/README.md), and the [Phase 6 review](planning/phase-6-review.md) |
| Preferences and profile lifecycle | [`apps/api/src/shopping/preferences/README.md`](../apps/api/src/shopping/preferences/README.md) and the [Phase 8 plan](planning/phase-8-implementation-plan.md) |
| Personal AI integration and privacy boundary | [`architecture/personal-ai-integration.md`](architecture/personal-ai-integration.md), [`apps/api/src/shopping/integrations/personal_ai/CONTRACT.md`](../apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), and [ADR 0003](adr/0003-personal-ai-boundary.md) |
| Frontend implementation | [`product/ux-design.md`](product/ux-design.md), `apps/web/src/`, and `apps/web/tests/` |
| Current phase, stop boundary, or next authorized scope | [`current-state.md`](current-state.md), then [`planning/implementation-plans-index.md`](planning/implementation-plans-index.md) and the selected phase plan |
| Cloud deployment and production operations | [`deployment/runbook.md`](deployment/runbook.md), [`planning/phase-9-implementation-plan.md`](planning/phase-9-implementation-plan.md), and the [Phase 9 verification record](deployment/phase-9-verification.md) |
| Validation, review, and external verification | [`../VALIDATION.md`](../VALIDATION.md), the owning phase plan/review, and `planning/*independent-review-handoff.md` where present. |

## Verification and links

From the repository root, `make validate` runs the deterministic lint, format, API, frontend, generated-type, typecheck, and build checks. PostgreSQL integration checks are separate and require a disposable database via `make test-db TEST_DATABASE_URL=...`. Use each phase plan for additional required checks. Do not describe unrun browser, live-provider, hosted, or cloud checks as passed.
