# Current implementation state

Updated 2026-10-07. This is the single living summary of implementation status; detailed evidence remains in the linked phase plans and [`VALIDATION.md`](../VALIDATION.md).

## Delivery boundary

- **Phases 0–5 — accepted.** Phase 5 has independent review and local verification. Live provider, hosted, and some manual browser checks remain outside the accepted local baseline; see the verification record.
- **Phase 6 — implemented locally; independently reviewed; not accepted.** Its repository gate remains open for PostgreSQL migration/integration checks and the planned browser journey/manual review. See the [Phase 6 review](planning/phase-6-review.md).
- **Phase 7 — implemented locally; review follow-up recorded; not accepted.** PostgreSQL lease/concurrency/recovery checks, browser journeys, provider behavior, and labeled quality/call-count measurements remain open. Local ID-based execution is provisional; measurements do not establish production suitability. See the [Phase 7 plan](planning/phase-7-implementation-plan.md) and [execution decision](architecture/research-execution-decision.md).
- **Phase 8 — implemented locally; independently reviewed; corrections and external verification open; not accepted.** PostgreSQL migration/lifecycle/model-drift checks and browser/manual journeys remain open. Review findings still need disposition before acceptance. See the [Phase 8 plan](planning/phase-8-implementation-plan.md) and [review handoff](planning/phase-8-independent-review-handoff.md).
- **Phase 9 — review corrections implemented locally; not accepted.** The 12 actionable review findings have local corrections and focused regression coverage. The full offline and PostgreSQL suites still contain unrelated Phase 5/8 failures; container execution, cloud IAM, browser journeys, provider behavior, and hosted backup/restore/security evidence remain open. Cross-instance generation ownership and deployed research/SSE lifecycle also remain open. Phases 6–8 retain their existing gates. See the [Phase 9 plan](planning/phase-9-implementation-plan.md), [runbook](deployment/runbook.md), and latest [verification record](../VALIDATION.md#phase-9-independent-review-corrections--2026-10-07).

## Current stop boundary and hard gates

The current user request authorizes local Phase 9 implementation. It does not authorize a hosted deployment or pass any earlier gate. Do not report Phases 6–8 as accepted. Before phase acceptance, close each phase's stated review and verification gates, and preserve predecessor-gate distinctions when later work is explicitly authorized.

The checked Personal AI contract does not provide structured shopping-task generation or user-scoped memory read/write/propose/retract APIs. Local deterministic fakes do not establish external compatibility or quality; no external memory adapter or writes are present.

A 2026-10-07 offline API run after the Phase 9 corrections had 3 failing cases: one product-planning context-budget case and two monetary-preference boundary/schema expectations. The full PostgreSQL suite also has six failures in existing conversation, preference, and product-research checks; one research failure passed when rerun alone. See the newest [`VALIDATION.md` entry](../VALIDATION.md#phase-9-independent-review-corrections--2026-10-07). These failures remain open and are not represented as Phase 9 regressions or passed gates.

## Latest verification evidence

[`VALIDATION.md`](../VALIDATION.md) is the chronological evidence record, not a startup guide. Its newest entry records the Phase 9 review corrections and the checks run; PostgreSQL and offline suite failures, browser review, live-provider/quality checks, hosted CI, and cloud checks remain open as described there and in the owning plans.

Status terms used here: **planned**, **locally started**, **implemented locally**, **independently reviewed**, **accepted**, **external verification open**, and **superseded**. Plans state intended work; only recorded evidence can establish what was run.
