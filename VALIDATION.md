# Validation record

## Phase 1 completion and evidence — 2026-10-03

Phase 1 was implemented on top of reviewed baseline `5ff030d` and committed in coherent slices: `0ff4fd1` (persistence/test harness), `c0aadc9` (service/API/generated types), and `6a1e673` (Home/Overview UI). The checkout is a local Git repository on `main`; `git remote -v` returned no configured remote, so GitHub-hosted CI could not be run. The planning docs record the contract and successor handoff.

| Check | Result |
|---|---|
| `make validate` and review follow-up | The original aggregate run passed with 9 frontend tests. After the conflict-reconciliation fix, all of its constituent checks passed again: Ruff check/format, ESLint, 17 deterministic API tests, 15 frontend interaction tests, generated-type check, TypeScript typecheck and Vite production build. The aggregate wrapper was not rerun because the available bundled pnpm 11.19.0 did not match the pinned 10.34.6 and tried to start an install, which aborted safely when it could not purge `node_modules` without a TTY. Database/live tests are explicitly excluded from this deterministic target. |
| `make api-types` then `make api-types-check` | Passed. Generated `packages/api-types/src/index.ts` matches the current FastAPI OpenAPI schema. |
| `make test-db TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test` | Passed: 15 PostgreSQL-marked tests against isolated PostgreSQL 16.15. Covers migration up/down/re-up, database constraints/types, durability, ownership, revision conflicts, tombstone and pagination. The fixture creates and drops uniquely named schemas and rejects the configured application database and unsafe database names. |
| `make migrate` with `DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_phase1_test` | Passed against a fresh disposable database in the isolated PostgreSQL cluster. |
| `uv run alembic check` with the same disposable `DATABASE_URL` | Passed: no new upgrade operations detected after migration. |
| Manual browser flow | In-app browser loaded Home; created “Vacuum for apartment” with USD 400 maximum, added two requirements, reordered them, refreshed and confirmed persistence, then archived and restored the project. At 390×844, Home and Overview rendered as single-column layouts; Overview document width matched the viewport, and keyboard focus moved from the route heading to the project-name field with a visible focus indicator. The native delete-confirm click exceeded the browser bridge timeout; UI tests verified confirmation/focus/tombstone behavior, and a real API request returned 204 followed by GET 404. |
| Accessibility/responsive checks | Interaction tests verify labels, focus after navigation, status/alert states, pending/duplicate submission, errors, retry, missing/deleted resources and conflict recovery. Responsive single-column rules exist at 860px and 600px. The 390px viewport and initial keyboard focus were manually verified; full keyboard-only traversal remains unverified. The browser bridge stopped responding after the native delete confirmation, so it could not reset its temporary viewport override or close the smoke tab. |
| Hosted/operational checks | GitHub Actions and its PostgreSQL 16 job were updated but not run on a hosted runner. `git remote -v` is empty. Docker Compose was unavailable in the Phase 0 environment and was not used for Phase 1; native PostgreSQL 16.15 provided DB validation. No cloud or credentialed provider calls are in scope. |

The local frontend environment used bundled Node 24.19.0 and pnpm 11.19.0; CI's Node 20 and pinned pnpm 10.34.6 installation path were not separately executed here. The workspace explicitly allows esbuild lifecycle scripts with `allowBuilds` (supported since pnpm 10.26). See the detailed [Phase 1 implementation plan](docs/planning/phase-1-implementation-plan.md) for acceptance-to-code mapping and limitations.

## Phase 1 conflict-reconciliation follow-up — 2026-10-03

The UI now rebases project and requirement drafts against the refreshed revision, sends only fields changed locally, and asks for a field-level choice when both versions changed the same field. A requirement deleted by another edit remains visible while it has a local draft. Save and delete stay paused when a 409 refresh fails. Regression coverage includes a second 409 followed by a failed refresh.

The constituent checks of `make validate` were run directly against the installed dependencies:

| Command | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run ruff check src tests migrations` | Passed. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run ruff format --check src tests migrations` | Passed: 49 files already formatted. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run pytest -m 'not db and not live'` | Passed: 17 tests. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run python ../../scripts/generate_api_types.py --check` | Passed: generated types are current. |
| `cd apps/web && node node_modules/vitest/vitest.mjs run` using bundled Node 24.19.0 | Passed: 15 tests. |
| `cd apps/web && node node_modules/eslint/bin/eslint.js .` using bundled Node 24.19.0 | Passed. |
| `cd apps/web && node node_modules/typescript/bin/tsc -b` using bundled Node 24.19.0 | Passed. |
| `cd apps/web && node node_modules/vite/bin/vite.js build` using bundled Node 24.19.0 | Passed: production bundle built. |

For the direct frontend commands, `node` was `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`. The wrapper install was not allowed to relink dependencies; the existing installation remained usable for these checks. The project lock pins pnpm 10.34.6, so use that version when running the aggregate wrapper later.

## Phase 1 independent-review fixes — 2026-10-03

The follow-up commits separate UI draft/pending-state organization from persistence and nested-resource invariants. The large overview module is now split into project draft/reconciliation helpers and requirement editor/forms. Save forms disable their editable controls while requests are pending, and submit handlers also reject duplicate project/requirement submissions. Missing or foreign-project requirement targets are checked inside the owner-scoped locked transaction before checking the expected revision, so those targets consistently return 404.

The ORM and new migration `0002_project_revision_notes` now enforce `revision >= 1` and nullable notes of at most 10,000 characters. The historical `0001` migration remains unchanged. The new migration was exercised against preexisting `0001` state, constraint violations, downgrade, and re-upgrade.

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff check src tests migrations` and `ruff format --check src tests migrations` | Passed. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m 'not db and not live'` | Passed: 17 deterministic tests. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run python ../../scripts/generate_api_types.py --check` | Passed; generated types remain current. |
| `cd apps/web && <bundled-node> node_modules/vitest/vitest.mjs run` | Passed: 17 UI tests, including delayed successful project save, requirement save and requirement create requests. |
| `cd apps/web && <bundled-node> node_modules/eslint/bin/eslint.js .`, `node_modules/typescript/bin/tsc -b`, and `node_modules/vite/bin/vite.js build` | Passed: lint, typecheck and production build. `<bundled-node>` is `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`. |
| `TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test uv run pytest -m db` | Passed: 23 tests against isolated PostgreSQL 16.15, including revision/notes constraint rejection, migration upgrade/downgrade/re-upgrade, and missing/foreign target 404 behavior with stale revisions. |
| Fresh disposable `shopping_phase1_review_test`: `uv run alembic upgrade head`, `uv run alembic check`, `uv run alembic heads` | Passed. Alembic found no new operations; head is `0002_project_revision_notes`. |

The available bundled pnpm version still differs from the locked wrapper version, so `make validate` was not used for this follow-up; its constituent deterministic checks are listed above. Browser, hosted CI and cloud/provider checks were not repeated and retain the limitations recorded earlier in this file.

## Phase 2 completion and validation — 2026-10-04

Phase 2 adds owner-scoped conversation persistence, a bounded shopping-intent task schema and deterministic fixtures, a lifespan-owned generation supervisor, attach-only SSE, atomic proposal confirmation, and a persisted-history assistant panel. The complete acceptance mapping is in the [Phase 2 implementation plan](docs/planning/phase-2-implementation-plan.md).

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest` | Passed: 33 deterministic tests. Pytest defaults exclude DB/live markers. Includes seven intent fixtures and structural checks for invalid IDs, budget, schema, context and response size. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test /opt/homebrew/bin/uv run pytest -m db` | Passed: 36 Phase 1 + Phase 2 tests against isolated local PostgreSQL 16.15. Covers migrations and ORM drift, owner scope, message replay/payload mismatch, concurrency, history cursor paging, no duplicate generation on reconnect, detached completion, restart interruption, proposal staleness, concurrent atomic apply/replay, dismissal and no project mutation on generation failures. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff check src tests migrations && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff format --check src tests migrations` | Passed; all 59 API source/test/migration files are clean and formatted. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run python ../../scripts/generate_api_types.py --check` | Passed; committed TypeScript types match OpenAPI. |
| `cd apps/web && /Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/vitest/vitest.mjs run` | Passed: 25 UI tests. Assistant coverage includes pending vs stale proposal controls, old/new requirement diffs, lost-ack replay using the same request key, draft recovery after revision conflict, older history paging, and keyboard focus/Escape close. SSE tests cover split UTF-8, multiline data, heartbeat comments and truncated terminal frames. |
| Direct bundled-Node ESLint, `tsc -b`, and Vite production build | Passed. The installed pnpm wrapper was 11.19.0 while the project pins 10.34.6, so checks used the existing dependencies without relinking or installing. `make validate` was not run as an aggregate. |
| Real Personal AI compatibility | Not run. The checked upstream route contract has chat text SSE but no verified structured shopping-task endpoint/schema. No endpoint was guessed; external mode returns sanitized `provider_unavailable`, and the fake is explicitly local-only. |
| Browser smoke, hosted CI, cloud/multi-instance behavior | Not run. The local supervisor is intentionally single-process, and Phase 9 must revisit execution lifetime before multi-instance hosting. The checkout has no configured Git remote for hosted CI. |

Default tests and configuration make no external calls. `--run-live` is recognized as an explicit pytest opt-in; no live compatibility test can pass until the upstream task contract and adapter are verified. The schema/prompt context is capped at 24,000 characters, accepted structured output at 256,000 characters, each user message at 8,000 characters, and concurrent in-process generations are capped by `CONVERSATION_MAX_CONCURRENT_GENERATIONS` (default 4). Prompt snapshots are removed once generation reaches a terminal state.

## Phase 2 independent-review fixes — 2026-10-04

Follow-up review tightened generated-output validation, generation-worker lifecycle, proposal owner/tombstone checks, frontend recovery and unsaved-draft protection, and fake-chair fixture semantics. `0004_proposal_applied_at` backfills already-applied proposals from `updated_at`; active-project gating now precedes replay and proposal locking follows project locking. Requirement and project patches are validated against the Phase 1 schemas before persistence, including the merged final budget. Exact replay remains before the revision check for active projects, while tombstoned or foreign projects return the scoped 404. Supervisor database work runs in worker threads with worker-owned sessions; cancellation waits for the owned database write to finish.

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest` | Passed: 39 deterministic tests; no external provider calls. Includes invalid-output rejection, absent/null semantics, deep and oversized data, explicit-unit fixture cases, and the dynamic budget question. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test /opt/homebrew/bin/uv run pytest -m db` | Passed: 50 PostgreSQL tests; includes migration `0004` backfill, live-project owner/tombstone gates across proposal states, rollback on invalid operation, atomic replay, and add/remove replacement at the 100-item limit. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff check src tests migrations && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff format --check src tests migrations` | Passed: clean lint and formatting. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run python ../../scripts/generate_api_types.py --check` | Passed; OpenAPI types include nullable `applied_at`. |
| `cd apps/web && /Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/vitest/vitest.mjs run` | Passed: 31 frontend tests, including definitive busy/capacity rejection recovery, uncertain retry-key retention, project-switch stream cancellation, dirty-requirement send/apply blocking and delayed-apply locking. |
| Direct bundled-Node ESLint, `node_modules/typescript/bin/tsc -b`, and `node_modules/vite/bin/vite.js build` | Passed. The installed pnpm wrapper is 11.19.0 while the project pins 10.34.6, so checks used installed dependencies without relinking. |
| Alembic `heads`, `upgrade head --sql`, and `bash scripts/validate_scaffold.sh` | Passed; migration head is `0004_proposal_applied_at`, the offline SQL includes the timestamp backfill, and the Phase 2 scaffold check passes. The PostgreSQL suite exercised fresh migration upgrade/downgrade/re-upgrade and ORM drift checks. |

`make validate` was not run as an aggregate because the local pnpm wrapper does not match the pinned version; all constituent offline checks are listed above. Browser smoke, hosted CI, multi-instance behavior, and live Personal AI compatibility were not run. The fake is deterministic test/local behavior, not evidence of external provider compatibility.

## Phase 3 bounded discovery — 2026-10-04

Phase 3 adds bounded owner-scoped discovery runs, the provider-neutral search/Tavily adapter, provisional candidates with preserved result lineage, and the project Discover route. The implementation-to-acceptance mapping and known external limits are in the [Phase 3 implementation plan](docs/planning/phase-3-implementation-plan.md).

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m 'not db and not live'` | Passed: 66 deterministic API/evaluation tests. Tavily HTTP behavior is exercised with mocked transport; default collection makes no external calls. Planner fixtures include category/constraint and exact decimal budget/currency omission checks. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test /opt/homebrew/bin/uv run pytest -m db` | Passed: 61 tests against the isolated PostgreSQL 16.15 test database. Research tests cover request replay/version gates, competing runs, ownership, budgets that include failed attempts, partial durability, result lineage, deadlines, cancellation/deletion/restart races and planner fallback. Migration tests upgrade, downgrade and re-upgrade fresh schemas and run Alembic's model-drift check. |
| Ruff and generated API types | Passed: `ruff check`, `ruff format --check` (81 API source/test/migration files) and `scripts/generate_api_types.py --check`. |
| Frontend | Passed: 37 Vitest tests, ESLint, TypeScript project build and Vite production build using bundled Node 24.19.0. The six Discover tests cover provisional rendering, duplicate submission, definitive rejection, uncertain acknowledgement replay, cancellation and empty/history states. |
| Manual desktop browser smoke | Passed on local fake configuration: opened a project, submitted an explicit manual query, observed running and terminal counters, and verified the empty result state and run history. The default fake intentionally returned no search results. Mobile viewport inspection was not run. |
| Aggregate/hosted/live checks | `make validate` was not run because the installed pnpm wrapper is 11.19.0 while the project pins 10.34.6; its applicable constituents above were run directly using installed dependencies. No Tavily credential or verified external structured-task endpoint was available, so live search and live Personal AI planning remain unverified. Hosted CI and multi-instance execution were not run. |

The manual browser smoke used only fake providers. It is evidence for the route and progress/empty-state interaction, not for search quality or returned products. Discovery execution is intentionally single-process and local until the later durable-job phase.

## Phase 0 baseline review and validation (historical)

Reviewed 2026-10-03 in `/Users/jasonkli/projects/shopping-assistant` before local Git history was established. The original supplied directory had no `.git`; it is now recorded at baseline commit `5ff030d`. No Phase 1+ functionality existed at the time of that review.

## Review result

Read README/handoff, all product/UX/roadmap, architecture/data/AI/search/research/deployment/testing, API, ADR and planning docs; inspected all source, tests, migrations, configuration, scripts and CI. The modular monolith boundaries match the intended design. Domain modules are placeholders, no domain tables exist, and `/health` is the sole API endpoint. PostgreSQL is prepared as authoritative storage; health deliberately does not query it.

Small corrections made:

- API settings now read root `.env` independently of working directory, with positive research limits and environment precedence. Alembic supports percent-encoded credentials.
- Fixed Ruff's deprecated collections imports; corrected the executor comment because closures cannot be dispatched remotely.
- Added frontend/API health connectivity with loading/error/retry and deterministic tests; fixed original Jest DOM/Vitest incompatibility and trailing API URL slash handling. Strict Vite port keeps default CORS coherent.
- Added Python/frontend lockfiles, pinned pnpm 10.34.6, explicit esbuild build allowance, compatible Jest DOM 6.9.1 and SQLAlchemy 2.0 range. Test command runs once.
- CI uses locked installs and checks migration environment/formatting; Make exposes install/migrate/typecheck/build/validate. Compilation script requires supported Python and uses writable ignored bytecode cache; TypeScript artifacts are ignored.
- Planning/API/roadmap/handoff distinguish present health scaffold from future capabilities. Generated file manifest excludes caches, dependencies and build products.

## Executed checks

| Check | Result and limits |
|---|---|
| `uv sync --extra dev`, then `uv sync --locked --extra dev --offline` | Passed, Python 3.12.13; lockfile generated/refreshed |
| pnpm 10 install, then `pnpm install --frozen-lockfile --offline` | Passed with explicit esbuild allowance; lockfile current |
| `make validate` | Passed: Ruff lint/format (35 Python files), pytest (5 tests), ESLint, Vitest (3 tests), TypeScript and Vite build |
| `bash scripts/validate_scaffold.sh`; shell syntax check | Passed for source/tests/migration compilation with Python 3.12+ |
| Alembic heads/offline upgrade | Passed; intentionally no revisions/domain tables |
| Alembic offline upgrade with `%25` credential in URL | Passed; ConfigParser escaping verified |
| PostgreSQL 16.15 online `alembic upgrade head`, `current`, `check` | Passed on isolated temporary native PostgreSQL, port 55439, UTF-8 test DB; no new upgrade operations detected |
| SQLAlchemy Session `SELECT 1` | Passed against that isolated PostgreSQL |
| Uvicorn startup and HTTP `/health` | Passed on temporary local port 58123; 200 `{"status":"ok"}` |
| CORS request from `http://localhost:5173` | Passed, exact origin header returned |
| Vite dev startup and HTTP HTML | Passed on temporary local port 58124; build also passed |
| Fake/offline boundaries | Passed offline import/execution smoke for AI echo, empty search, retrieval success/missing fixture and in-process executor; intentionally minimal, no live task behavior claimed |

Temporary API/Vite/PostgreSQL processes were stopped. Dependencies, `.venv`, `node_modules`, ignored caches/build output remain available locally; they are excluded from manifest/source deliverables.

Toolchain: Python 3.12.13, uv 0.11.13, pnpm 10.34.6, bundled Node 24.19.0, PostgreSQL 16.15. CI specifies Python 3.12 and Node 20; Node 20 compatibility was not separately executed. `uv` cache and Node/pnpm paths were adjusted for this sandbox. A first install attempt failed under restricted DNS, then approved network installation succeeded. The system `python3` is 3.9.6 and its default bytecode-cache path was unwritable; the revised script avoids both pitfalls. A first frontend install used bundled pnpm 11 and was replaced with pnpm 10 to match CI. A first PostgreSQL port was occupied; an isolated alternate port was used. These initial failures were resolved before the final checks.

The ten plans were cross-reviewed for ordering, schema/API/provider handoffs, ownership, revisions, idempotency, evidence and deployment lifecycle. All 10 phase files and index exist, relative Markdown links resolve, and JSON/TOML/YAML configuration plus source-only manifest paths parse/validate. These documentation checks do not assert future features are implemented.

## Remaining verification and known warnings

- Docker executable/Compose runtime was not available on PATH; Compose PostgreSQL startup/health was not run. Native PostgreSQL validates DB/Alembic behavior, not Compose behavior.
- At the original Phase 0 review, real-browser frontend → API connectivity, keyboard/mobile visual inspection, and API-stop/retry recovery were not manually exercised. The Phase 1 browser flow/responsive checks are recorded above; a focused Phase 0 health retry remains unverified.
- At the original Phase 0 review, GitHub Actions could not be run because the extracted directory had no Git metadata. The current local workflow was updated in Phase 1 but remains unrun on a hosted runner; this checkout has no configured remote. CI Node 20 has not been checked locally.
- No real Personal AI, Tavily/Brave, HTTP page retrieval, Firebase, Cloud Run, Neon, authentication or cloud deployment checks were run. Those adapters/features are not implemented in Phase 0.
- The resolved FastAPI/Starlette test client warns that its httpx integration is deprecated. Tests pass using the declared httpx dependency; do not add an unrelated transport migration without a concrete compatibility need. Resolved ESLint 9 and a jsdom transitive package emit deprecation warnings. No security audit or dependency upgrade exercise was performed/claimed.

## Reproduction

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
make install
make validate
bash scripts/validate_scaffold.sh
make db-up
make migrate
cd apps/api
uv run alembic check
uv run uvicorn shopping.main:app --reload --host 127.0.0.1 --port 8000
# Separate terminal, repository root:
make web
```

Do not report remaining checks passed until actually run. Follow [Phase 0 plan](docs/planning/phase-0-implementation-plan.md) for only these verification gaps; follow the [index](docs/planning/implementation-plans-index.md) for future implementation.
