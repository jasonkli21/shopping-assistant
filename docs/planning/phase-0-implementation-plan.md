# Phase 0 — Corrected foundation

Status: scaffold corrections complete on 2026-10-03; external foundation verification remains below. This is a record and limited follow-up plan, not an instruction to rebuild completed scaffolding. Read the [index](implementation-plans-index.md), [validation record](../../VALIDATION.md) and ADRs 0001–0004.

## Outcome and baseline

A developer can run a React/TypeScript SPA, FastAPI health API and PostgreSQL, with migrations/tooling prepared and external provider boundaries separated. No shopping workflow, domain tables, authentication, live AI/search or research orchestration is implemented.

The smallest slice is browser → health client → FastAPI `/health`; PostgreSQL connectivity is verified separately because health is liveness, not database readiness. The API has one route and the UI is a scaffold landing page with loading, connected, error and retry states.

## Completed work and contracts

- Backend source is `apps/api/src/shopping/`; tests are `apps/api/tests/`. Domain packages are reserved. SQLAlchemy Base/session and Alembic environment/template/empty versions directory exist; zero domain migrations is intentional.
- React Router and TanStack Query are wired in `main.tsx`. Health uses Query and the typed fetch client; Vite port 5173 is strict so CORS stays coherent. `VITE_API_BASE_URL` is build/dev configuration in `apps/web/.env.local`; it is not a secret.
- Typed API settings load repository-root `.env` independently of the command's working directory; process environment overrides it. Positive research limits and comma-separated origins are validated/parsed. Alembic escapes percent-encoded credentials for ConfigParser.
- SQLAlchemy is limited to the selected 2.0 line. `apps/api/uv.lock`, `apps/web/pnpm-lock.yaml` and pinned pnpm 10 make installs reproducible. Only esbuild dependency builds are allowed. Jest DOM uses its Vitest entry point; tests execute once through `pnpm test` (`test:watch` is optional).
- Ruff import error corrected. CI uses locked installs, backend lint/format/tests/offline Alembic and frontend lint/typecheck/tests/build. Make targets expose installation, migration and complete validation. Compilation script requires Python 3.12+ and places caches in an ignored writable directory.
- `PersonalAIClient.generate(AIRequest) -> AIResponse` is an asynchronous minimal protocol with unvalidated dictionary payloads; task schemas arrive in Phase 2. Its fake echoes inputs and is not an intent engine.
- `SearchProvider.search(SearchQuery) -> list[SearchResult]` is neutral and asynchronous; fake returns no results. Fixture-backed discovery behavior arrives in Phase 3.
- `PageRetriever.retrieve(url) -> RetrievedDocument` returns raw content, not extracted facts. Its fixture fake raises `LookupError` on a missing document; extraction tasks arrive in Phases 4–5.
- `ResearchExecutor.execute(context, work) -> result` simply awaits in-process work and propagates errors. Its callable cannot be serialized; comment now explicitly requires ID-based evolution before Phase 7 remote execution.

## Ordered follow-up packages

### 0A — Verify the corrected checkout on a normal developer machine

Do not recreate files above. Install locked dependencies and run the index commands. Start Compose PostgreSQL 16 and check `docker compose ps`/health. With no domain migrations, `make migrate` creates only Alembic's bookkeeping; `alembic check` should find no model changes. Start API and web in separate terminals, visit the landing page, stop API and use retry after restarting. Test a narrow mobile viewport and keyboard access to retry.

Acceptance: locked install, `make validate`, migration environment, browser health/error/recovery and Compose startup succeed. A DB failure must not be misreported as `/health` failure; database readiness is added with deployment later.

### 0B — Close verification gaps and preserve the phase boundary

The original Phase 0 review used an extracted directory without `.git`. Git is now available locally: baseline `5ff030d` records that reviewed scaffold, with Phase 1 commits following it. `git remote -v` currently returns no remote, so hosted workflow status cannot be inspected or run from this checkout. Generated artifact manifest excludes caches/dependencies/build products. Existing placeholder modules and frontend feature folders need no architecture framework.

Acceptance: validation record has honest statuses and the plans/docs are linked; any actual foundation failure is fixed narrowly with evidence. Stop before project models/endpoints/UI.

## Verification, commits and handoff

Phase 0 checks and limitations are recorded historically in `VALIDATION.md`; PostgreSQL 16 online checks used an isolated temporary native instance, not Docker Compose. HTTP health/CORS and Vite startup passed. The later Phase 1 browser smoke exercised the real web/API project flow, but a focused Phase 0 health retry and keyboard/mobile visual check remains unverified. Hosted CI and deployed/provider checks were not run.

Suggested commit boundaries when Git is available: (1) settings/migration/tooling/lock corrections and focused tests, (2) health connectivity and frontend test repair, (3) review record and plans. Preserve existing edits rather than resetting the checkout.

Completion review: Is each documented command correct? Are lockfiles present? Does the frontend surface connectivity failure? Does Alembic read the same URL as the app, including encoded passwords? Are provider interfaces intentionally minimal and local execution described accurately? Are source/test directories clean? Are unrun checks visibly unrun?

Original handoff to Phase 1: this exact health slice, Base/session/Alembic setup, locked dependency/toolchain versions, module boundaries and deterministic baseline. Phase 1 has since added the first domain migration and project workflow. Phase 0-specific Compose startup, focused health retry and hosted CI checks remain unverified; no unresolved architecture choice blocked Phase 1.
