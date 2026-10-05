# Shopping Assistant implementation plans

Reviewed 2026-10-04 after Phase 5 local implementation. Phases 0–5 are implemented locally; Phase 5 awaits independent main-session review and Phases 6–9 remain plans. Read [validation](../../VALIDATION.md) and [handoff](../../CODEX_HANDOFF.md) before selecting a phase. The original [roadmap outline](implementation-plan.md) remains a summary.

## Sequence and gates

| Phase | Outcome and prerequisite | Plan | Status |
|---|---|---|---|
| 0 | Corrected, validated foundation | [Foundation](phase-0-implementation-plan.md) | Code corrections complete; Docker/browser/hosted CI checks remain |
| 1 | Durable manual projects and requirements; uses 0 | [Projects](phase-1-implementation-plan.md) | Implemented and locally validated; 390px responsive view and initial keyboard focus verified; full keyboard traversal and hosted CI remain unverified |
| 2 | Inspectable intent proposals and conversation; uses 1 | [Intent](phase-2-implementation-plan.md) | Implemented and locally validated; upstream structured-task contract/live compatibility and manual browser smoke remain pending |
| 3 | Bounded discovery and persisted candidates; uses 1–2 | [Discovery](phase-3-implementation-plan.md) | Implemented and locally validated; live Tavily and Personal AI remain unverified |
| 4 | Canonical product/variant/offer identities; uses 3 | [Normalization](phase-4-implementation-plan.md) | Implemented and locally validated; live page coverage and browser smoke remain unverified |
| 5 | Multi-source claims, evidence and assessments; uses 4 | [Evidence](phase-5-implementation-plan.md) | Accepted after main-session review and local verification; live/provider/browser/hosted checks unverified |
| 6 | Complete decision journey; uses 1–5 | [MVP](phase-6-implementation-plan.md) | Planned; mandatory repository-wide gate |
| 7 | Durable job reliability and deeper research; requires signed-off 6 gate | [Orchestration](phase-7-implementation-plan.md) | Planned; remote execution conditional |
| 8 | Explicit persistent preferences and optional external memory; uses 7 | [Memory](phase-8-implementation-plan.md) | Planned |
| 9 | Authorized and verified cloud deployment; uses 1–8 | [Production](phase-9-implementation-plan.md) | Planned |

Complete one phase and stop. Read successor handoff requirements before implementing the selected phase, but do not implement its successor. A predecessor's failed acceptance criterion remains a blocker or an explicitly documented limitation; a plan is never evidence that code exists. Phase 6 requires a comprehensive product, architecture, data, code, privacy, and testing review plus resolution of blocking findings before Phase 7.

## Shared implementation rules

- Keep the modular monolith, React/TypeScript SPA, FastAPI, SQLAlchemy 2.0, PostgreSQL 16 and Alembic. Category attributes use bounded JSONB; never move shopping state into Personal AI memory or Firestore.
- Source: `apps/api/src/shopping/` and `apps/web/src/`. Tests/fixtures/evals: `apps/api/tests/` and `apps/web/tests/`. New domain service, repository and transport files live within the owning module; avoid speculative generic frameworks or repository base classes.
- `api/` aggregates routers and transport concerns; domain modules own their validation/services. Research coordinates explicit project/catalog/evidence services. Provider adapters depend on neutral contracts, and never on domain orchestration. Shopping prompts and output schemas belong to the shopping task's module. Personal AI alone invokes model providers.
- UUID identifiers, timezone-aware UTC timestamps, explicit enum validation and stable ordering. JSON monetary values are decimal strings plus ISO currency, stored as `NUMERIC`, never float. Missing means unknown, not zero/false. No currency conversion or total-cost invention.
- Use a stable server-side local principal in early phases, with `owner_id` on project/private state. Never trust a client-supplied owner. Before cloud exposure, Phase 9 maps authenticated identities to owners. Early unauthenticated development binds to localhost; it is not a public deployment mode.
- Project revisions start at 1. All project-context writes carry `expected_version`; stale changes return 409 and current revision. A service transaction validates references, applies changes and increments once. Requirement/decision/comparison writes also advance the project revision. Message/run/provider activity records do not increment project-context revision. Derived state created by a context write records the committed revision, not the pre-write value. Research/AI runs snapshot that revision; external I/O never holds database transactions open. Results may be retained but stale-context assessments/proposals may not overwrite newer edits.
- API errors use `{error:{code,message,details?,request_id?}}`; invalid fields 422, missing or foreign-owner resources 404, revision/invalid-transition conflict 409, provider failures are sanitized. Pagination uses a bounded `limit` (default 20, maximum 100) and an opaque cursor with deterministic ordering.
- A `request_key` on conversation/research commands is unique within owner/project/command type. Persist request payload hash and result ID; same key/body returns that command, differing body returns 409. Check exact command replay before current revision validation so an acknowledged command remains replayable after subsequent edits. Normal human edit retries can rely on revision conflicts; do not build universal idempotency middleware.
- Run/job IDs are first-class. Phase 3 runs persist their command before returning 202 and persist query attempts/results/candidates before terminal completion; Phase 7 jobs refine execution, not a second research domain. Phase 0 `execute(context, callable)` is explicitly local-only. Remote dispatch requires serializable persisted IDs in Phase 7.
- Phase 3 candidates are unverified search observations, not canonical products, sources successfully retrieved, validated facts or offers. Phase 4 maps candidates to Product → ProductVariant → RetailOffer; Phase 5 creates retrieved source snapshots, claims/evidence and project-relative assessments. Decision references point to `ProjectProduct`, which specifies a variant.
- Snapshot offers with observation time, retailer, URL, condition, availability, amount and currency. Preserve observations across refreshes. Claims have exact source/excerpt provenance; AI assessments cite claim IDs; user notes/corrections are user judgments. No opaque universal product score.
- SSE is for interactive assistant text and status, never an unvalidated mutation transport. Persist validated proposal/terminal state; disconnect/reconnect must not duplicate work. Research progress initially uses polling, avoiding an unnecessary second stream infrastructure.
- Normal CI uses task-shaped deterministic Personal AI fakes, search fixtures and retrieved-page fixtures. Real PostgreSQL integration is offline with respect to external providers. Credentialed/provider/cloud/manual-browser checks are separate and explicitly recorded as passed, failed, or not run. Dependency installation may require a registry network; tests must not depend on that network.
- No Redis, Celery, Kafka, Pub/Sub, OpenSearch, Kubernetes, vector store or general browser automation. Add Cloud Run Jobs only after Phase 7's measured decision gate. Do not add later lifecycle/capture/payment features.

## Verification and evidence conventions

Existing commands, from repository root:

```bash
make install                 # registry access on first install; lockfiles required
make validate                # backend lint/format/test; frontend lint/test/typecheck/build
bash scripts/validate_scaffold.sh
make db-up                   # requires Docker
make migrate                 # online Alembic; root .env config
cd apps/api
uv run alembic heads
uv run alembic upgrade head --sql
uv run alembic check          # online, after upgrade; model imports must be complete
```

Phase 1 establishes the test split: default CI/`make test` excludes `db` and `live`, while `make test-db TEST_DATABASE_URL=...` runs against isolated schemas inside a disposable, explicitly named PostgreSQL database. Its CI job provisions PostgreSQL 16. Phase 2 introduces `live` opt-in collection/execution guarded by an explicit `--run-live` option plus dedicated provider configuration (use `uv run pytest -m live --run-live`); no credentialed calls during default `pytest`. Each plan specifies its additional tests/evals and manual checks. `make validate` remains deterministic and explicitly reports that PostgreSQL integration tests run separately.

After every phase, update that phase's status with a table mapping acceptance criterion → actual files/contracts → executed command/test → result, plus date, commit if available, and outstanding external checks. Record architectural changes in the relevant doc/ADR only when actually justified. Keep API draft and generated TypeScript types aligned. Do not mark provider/cloud checks passed based on fixtures. Retain a concise handoff of contracts, migrations and limitations for the successor.

## Cross-phase consistency review, 2026-10-03

The ten plans were reviewed together against the source and ADRs, including route inventory, owner scoping, revision snapshots, provider/task introduction, schema handoffs, test commands and deployment lifecycle. Resolved sequencing gaps:

1. Local ownership and revisions begin with projects, allowing later authorization without replacing project identity.
2. Phase 2 produces validated proposals with explicit application, reused for Phase 6 decision commands; prose never becomes durable state.
3. Phase 3 introduces candidate observations; Phase 4 alone introduces catalog identity and migrates/maps existing candidates. No early endpoint pretends candidates are products.
4. Phase 4 uses a small retrieval implementation for identity/offer extraction. Phase 5 extends the same boundary for evidence; it does not introduce a competing retriever or catalog normalizer.
5. Research runs, attempt records and bounded execution begin in Phase 3. Durable scheduling/leases arrive in Phase 7; distributed adapters remain conditional.
6. Product facts, attributed claims, assessments, offers and user corrections remain distinct through comparison and refresh.
7. Phase 6 favorites/purchased state is local shopping state. Phase 8 explicitly promotes preferences and optionally proposes memory; neither implies automatic cross-application writes.
8. Phase 9 authenticates existing owner-scoped data and verifies the entire hosted MVP, not merely container health. Job deployment is conditional on Phase 7 evidence.

Comparison creation records its committed revision to avoid instant staleness. Run/message status does not change shopping context revision. Phase 9 explicitly revisits conversation execution ownership and in-memory stream state before multi-instance cloud exposure. Normal CI marker selection separates database/live checks instead of skipping them ambiguously. No circular prerequisite or extra infrastructure is required. Actual Personal AI wire capabilities, provider credentials/quotas, cloud account settings and any need for remote jobs remain external checks at their owning phase. They do not block Phase 1. No attached implementation guide was available in this checkout/session; depth follows the supplied review criteria and repository design docs.

## Reusable Luna Max prompt

> Implement only Phase N using `docs/planning/phase-N-implementation-plan.md` and the shared contracts in `docs/planning/implementation-plans-index.md`. First read `README.md`, `CODEX_HANDOFF.md`, the selected plan, its predecessor's completion evidence, and referenced product/architecture/API/ADR docs. Reconcile the plan against the current code and tests; distinguish completed work, missing work and external dependencies. Preserve the established architecture and implement the smallest complete phase outcome, including migrations, failure behavior and UX. Satisfy every acceptance criterion and run the plan's verification with deterministic fakes and real PostgreSQL where specified. Record plan → code → test evidence, command results, remaining risks and genuinely unrun provider/cloud/credentialed checks; update phase status, API/docs and successor handoff. Resolve review findings within this phase, commit in coherent boundaries if Git is available, and stop. Do not begin Phase N+1. For Phase 6, complete and document the mandatory repository-wide review gate before allowing Phase 7.
