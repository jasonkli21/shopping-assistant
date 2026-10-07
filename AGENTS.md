# Agent operating contract

Shopping Assistant is a personal research and decision-support app that ends at an evidence-backed shortlist. Checkout, payment, and automated purchasing are out of scope. Keep changes within the authorized task or phase; a plan describes scope but does not prove delivery or authorize its successor.

## Authority and architecture

Resolve disagreements in this order: code, executable contracts, migrations, and tests; release/review/verification evidence; accepted ADRs; architecture and product docs; active plans; historical notes. Security and privacy constraints take precedence. Follow the current user request when it explicitly changes scope, but never rewrite prior evidence to make an earlier gate appear passed.

- Keep a modular monolith. Shopping-domain state belongs in PostgreSQL; schema changes use ordered Alembic migrations that preserve existing data and have migration coverage.
- Keep Personal AI behind `PersonalAIClient`. Shopping-domain code must not call model providers directly. Keep search, page retrieval, and research execution behind `SearchProvider`, `PageRetriever`, and `ResearchExecutor` respectively.
- Keep application source in `apps/api/src/` and `apps/web/src/`; tests, fixtures, and evaluations belong in their test directories.
- Enforce hard project constraints deterministically before accepting or presenting results. AI suggestions cannot silently weaken or mutate them.
- Preserve provenance and revisions for durable changes. Use optimistic concurrency for project context, exact replay/idempotency for accepted commands, and immutable evidence/decision history where the owning contract requires it. Keep AI proposals inspectable and explicitly applied; never treat an AI inference or plan as verified fact.

## Working rules

- Route documentation by task through [`docs/README.md`](docs/README.md). Use [`docs/current-state.md`](docs/current-state.md) for the single living status summary.
- Phase plans are future-work contracts; verification records show what ran. A locally implemented or independently reviewed phase is not accepted until its stated gates are met.
- `CODEX_HANDOFF.md` and `docs/planning/coordinator-state.md` are compatibility redirects, not architecture. Model/session handoffs and historical notes are not canonical instructions.
- Prefer existing types, tests, and linters to new prose or enforcement frameworks. Do not add infrastructure or product behavior outside the authorized scope.

## Verification

Use the selected plan's checks. The normal deterministic repository suite is `make validate`; PostgreSQL checks use `make test-db TEST_DATABASE_URL=...` with an explicitly disposable database. For schema/API work, also use `make api-types-check` and the migration checks in the selected plan. Record external, browser, provider, and hosted checks as open unless actually completed. `VALIDATION.md` is evidence history, not required startup reading.
