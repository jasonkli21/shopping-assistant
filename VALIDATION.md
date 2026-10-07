# Validation record

This file is chronological verification history, not current status or required fresh-session reading. For the live implementation boundary, see [`docs/current-state.md`](docs/current-state.md); for task-routed context, see [`docs/README.md`](docs/README.md).

Latest records: [Phase 9 independent review corrections](#phase-9-independent-review-corrections--2026-10-07), [Context architecture cleanup verification](#context-architecture-cleanup-verification--2026-10-07), [Phase 8 implementation baseline](#phase-8-local-implementation-checks--2026-10-05), [Phase 7](#phase-7-implementation-checks--2026-10-05), and [Phase 6](#phase-6-implementation-and-verification--2026-10-05). Older phase records below remain historical evidence.

## Phase 9 independent review corrections — 2026-10-07

The 12 actionable findings documented in the Phase 9 independent review handoff have local implementation corrections and focused regression coverage. These changes do not accept Phase 9 or close the separately listed hosted release work, predecessor gates, or external checks.

| Check | Result |
|---|---|
| Focused offline review checks | Passed: 23 tests covering production/operator configuration, Firebase auth error classification and session lifetime, private route ownership, request-log redaction, privacy CLI refusal paths, and the explicit requirement-kind prompt boundary. |
| Focused PostgreSQL review checks | Passed: 13 tests covering migration upgrade/downgrade/re-upgrade and legacy revision aliases, privacy export/purge snapshot and concurrency behavior, readiness, and SSE lifetime logs. Two non-database tests in the selected files were deselected. |
| API Ruff lint and formatting | Passed: `ruff check src tests migrations` and `ruff format --check src tests migrations`; 167 files formatted. |
| API generated types | Passed: `scripts/generate_api_types.py --check`; TypeScript API types match the OpenAPI contract. |
| Alembic offline SQL | Passed through `p9_owner_privacy_lifecycle`. Offline generation does not replace online migration execution; online fresh, downgrade/re-upgrade, and legacy alias paths passed in the focused PostgreSQL tests. |
| Full offline API suite | 177 passed, 3 failed, 112 deselected. Failures: `test_full_requirement_snapshot_stays_plannable_without_dropping_assessment_data`, `test_preference_boundary_scenarios[category budget does not cross categories]`, and `test_money_preferences_require_category_and_currency`. These remain open product-planning and Phase 8 preference-boundary issues. |
| Full PostgreSQL suite | 105 passed, 6 failed, 179 deselected. Failures: `test_oversized_project_context_is_saved_as_failure_without_provider_call`, `test_explicit_candidate_promotion_reuse_edit_and_revoke`, `test_product_research_assesses_all_one_hundred_requirements`, `test_malformed_planner_output_is_terminal_and_inspectable`, `test_product_research_persists_grounded_claim_and_cited_assessment`, and `test_runtime_contexts_retain_both_quotes_and_cite_only_comparable_result`. The malformed-planner case passed when rerun alone; the other conversation, preference and product-research failures remain open predecessor issues. |
| Container build/runtime and CI smoke | Not run locally because Docker is unavailable. CI now builds the image and checks health plus fail-closed readiness from `/tmp`; the hosted workflow has not run for this change. |
| Browser, Firebase/GCP IAM, Neon, live provider, hosted backup/restore and deployment checks | Not run. No cloud resources were created or deployed; these remain open in the runbook and Phase 9 plan. |
| Aggregate `make validate` | Not run. The changed API checks were run directly; no frontend source changed. |

The local corrections cover packaged import/readiness paths, Alembic version width and legacy IDs, short-lived Firebase binding lookup, purge write fencing and cascade-aware counts, repeatable-read export, a complete operator export/purge path beyond HTTP caps, explicit INFO and SSE lifetime logging, Firebase IAM/error guidance, production container defaults, cloud administrative URL validation, and executable regression cases. See the handoff for the full findings and the [current-state summary](docs/current-state.md) for the remaining stop boundary.

## Context architecture cleanup verification — 2026-10-07

This documentation-only change adds the canonical agent contract, documentation router, current-state page, and research module guide; it does not change shopping behavior. Relative Markdown file links resolved, `git diff --check` passed, API Ruff/format passed, generated API types were current, the scaffold source compile passed, and direct frontend tests (64), ESLint, TypeScript, and Vite production build passed. Vite emitted its existing advisory that the main chunk exceeds 500 kB.

The aggregate `make validate` could not finish because pnpm attempted to fetch the pinned version from the unavailable registry and could not replace `node_modules` without a TTY. Direct offline API tests collected 164 and finished with 160 passed and 4 failed:

- `test_full_requirement_snapshot_stays_plannable_without_dropping_assessment_data`
- `test_preference_boundary_scenarios[category budget does not cross categories]`
- `test_preference_boundary_scenarios[soft profile conflict keeps hard project requirement in assistant context]`
- `test_money_preferences_require_category_and_currency`

These failures leave relevant research/preference correctness open; they were not changed as part of this documentation cleanup. No PostgreSQL or browser journey checks were run. The Phase 8 record below is the earlier implementation baseline, not a replacement for this newer result.

## Phase 8 local implementation checks — 2026-10-05

Phase 8 implements an owner-scoped local shopping profile, explicitly reviewed candidates from a saved project preference or rejected-product judgment, bounded category-scoped suggestions, opt-in per-project reuse, and source provenance on applied project requirements and snapshots. It proceeded at the user's explicit direction while the Phase 6 gate and Phase 7 acceptance remain open; this record does not close either predecessor gate.

Implementation commits: `98b415b` (API/persistence/evaluations) and `e08e485` (frontend). Documentation is recorded separately.

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run --extra dev pytest -m 'not db and not live'` | Passed: 164 tests, including preference boundary evaluations for compact furniture, desk-height locality, category budgets, one-time must-haves, rejected judgments, revocation and hard/soft conflicts. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run --extra dev ruff check src tests migrations` and `ruff format --check src tests migrations` | Passed; all 154 API source/test/migration files are lint-clean and formatted. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run --extra dev python ../../scripts/generate_api_types.py --check` | Passed; FastAPI contracts and `packages/api-types/src/index.ts` match. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run --extra dev alembic upgrade head --sql` | Passed; generated offline SQL through migration `0019_explicit_shopping_preferences`. This does not execute the migration against PostgreSQL. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run --extra dev pytest -m db --collect-only` | Passed collection: 104 database tests, including the Phase 8 schema and preference lifecycle cases. The tests were not executed. |
| `cd apps/web && <bundled-node> node node_modules/vitest/vitest.mjs run` | Passed: 64 tests across 7 files, including Shopping Profile revoke behavior and explicit rejected-judgment candidate creation. |
| `cd apps/web && <bundled-node> node node_modules/eslint/bin/eslint.js src tests`, `node_modules/typescript/bin/tsc -b`, and `node_modules/vite/bin/vite.js build` | Passed: ESLint, TypeScript and production build. Vite reports the main JavaScript chunk at 510.65 kB minified, above its 500 kB advisory threshold. `<bundled-node>` is `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`. |
| PostgreSQL migration/lifecycle/model-drift tests | Not run. `TEST_DATABASE_URL` is unset; local PostgreSQL cluster initialization fails to allocate shared memory (`shmget`, “No space left on device”). |
| Browser journey/manual responsive and keyboard review | Not run. Automated UI tests use deterministic fetch fakes and are not browser E2E evidence. |
| Personal AI memory, live model/provider, retailer/source, hosted CI and cloud checks | No user-scoped Personal AI memory CRUD/proposal/retraction contract was found, so no adapter or external writes exist. Live/provider, hosted CI and cloud checks were not run. |

The repository-pinned pnpm bootstrap attempted to fetch pnpm 10.34.6 from the unavailable registry. Installed dependencies were checked directly with the bundled Node runtime. The feature is implemented locally but not accepted; the Phase 6 gate and Phase 7 acceptance remain open.

## Phase 7 implementation checks — 2026-10-05

Phase 7 is implemented locally at the user's explicit direction while the Phase 6 repository gate remains open. This records static/schema checks only; no tests were run for this implementation, and Phase 7 is not accepted.

Implementation commits: `0f6b708` (API, persistence, execution and refresh behavior) and `22c4e3b` (frontend and generated API types). Documentation is committed separately.

| Check | Result |
|---|---|
| API lint and formatting | `UV_CACHE_DIR=/private/tmp/shopping-assistant-uv-cache uv run ruff check src migrations` and `UV_CACHE_DIR=/private/tmp/shopping-assistant-uv-cache uv run ruff format --check src migrations`: passed; 114 files formatted. |
| API schema/types | `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-assistant-uv-cache uv run python ../../scripts/generate_api_types.py --check`: passed; generated types are current. |
| Frontend TypeScript | `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/typescript/bin/tsc -b --pretty false` from `apps/web`: passed. |
| Migration SQL generation | `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-assistant-uv-cache uv run alembic upgrade head --sql`: passed and generated through `0018_research_offer_observations`. This does not execute migrations against PostgreSQL. |
| Whitespace/diff check | `git diff --check`: passed. |
| API, frontend, database and browser tests | Not run for this implementation. In particular, no Phase 7 PostgreSQL lease/concurrency/recovery tests or retry/refresh browser journey were run. |
| Live provider and quality measurements | Not run. No provider duration/cost sample or labeled Phase 5/6 quality and call-count comparison is available. |

PostgreSQL execution of migrations `0015`–`0018`, claim contention, restart and late-worker fencing remain unverified. The local executor decision is provisional because no measured execution-window or deployment-lifecycle evidence justifies remote execution. See the [Phase 7 implementation record](docs/planning/phase-7-implementation-plan.md) and [executor decision](docs/architecture/research-execution-decision.md). These checks do not close the Phase 6 gate.

## Phase 6 implementation and verification — 2026-10-05

Decisions and audit events, owner-scoped project/product notes, independent favorites, saved comparison dimensions/snapshots, workspace UI and explicit v2 assistant proposal actions are implemented locally. The repository-wide gate is **open, not passed**. Findings and dispositions are in [the Phase 6 review](docs/planning/phase-6-review.md).

| Check | Result |
|---|---|
| Offline API and eval suite | `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache uv run pytest -m 'not db and not live'`: 133 passed, 97 database/live tests deselected. Includes comparison unit normalization, unsupported-unit equality and unknown-value regressions. |
| API lint and formatting | `ruff check src tests migrations` and `ruff format --check src tests migrations`: passed; 133 Python files are formatted. |
| API schema/types | App OpenAPI import succeeded with 39 paths, including Phase 6 decisions, notes, favorites and comparisons. `scripts/generate_api_types.py --check` passed; committed TypeScript transport types match OpenAPI. |
| Migration generation | `alembic upgrade head --sql` passed and emitted the full upgrade chain through `0013_mvp_decisions_comparisons`. This checks SQL generation only, not execution against PostgreSQL. |
| PostgreSQL integration/migration checks | Not run. A disposable PostgreSQL 16 cluster attempt, including an escalated attempt with mmap primary shared memory, failed during `initdb` with `shmget: No space left on device`. Consequently `pytest -m db`, online migration, downgrade/re-upgrade and `alembic check` remain unverified. |
| Frontend interaction suite | 57 Vitest tests passed across 6 files, including 4 Phase 6 tests for note-save failure/draft preservation, independent favorites, shortlist transitions and comparison conflict recovery. |
| Frontend quality/build | ESLint, TypeScript project check and Vite production build passed using the bundled Node runtime. |
| Aggregate validation wrapper | `make validate` was not run: the available fallback pnpm is 11.19.0 while the repository pins 10.34.6 and attempts an interactive install. Each deterministic constituent check was run directly. |
| Browser E2E/manual journey | Not completed. No Playwright package or browser executable is installed, and the Phase 6 `pnpm test:e2e` suite has not been added. Desktop/mobile journey, keyboard-only use, citations and provider failure/recovery remain unreviewed in a browser. |
| Live provider/source audit | Not run; deterministic fakes establish local task behavior only. Hosted CI, cloud deployment and multi-instance checks were also not run. |

The offline review caught and fixed a comparison equality bug where unsupported numeric units were omitted from the equality key; units now participate in equality unless a deterministic conversion is defined, and decimal values use stable canonical formatting. Phase 6 acceptance remains open until the PostgreSQL and browser journey checks above are completed. Phase 7 was subsequently implemented at the user's explicit direction; that work does not pass or waive this gate.

## Phase 5 local implementation — 2026-10-04

Selected-product runs persist bounded plans, source retrieval attempts and short immutable snapshots; exact validated claims feed contextual relations and requirement-linked cited assessments. The Phase 5 review fixes tighten quote, qualifier, measurement, source-class and variant-identity grounding; make terminal skips, deadline failures and canceled writes inspectable; isolate ProductResearch query state and preserve exact command replay after uncertain acknowledgements; page assessment history; and support the full 100-requirement limit. Phase 5 was accepted after main-session review; Phase 6 verification is recorded above.

| Check | Result |
|---|---|
| Offline API/evidence evals | `pytest -m 'not db and not live'`: 130 passed; `pytest tests/evals/evidence`: 33 passed. Coverage includes quote-verifiable bound/qualifier semantics, type-checked normalized values, sentence-local attribute grounding, nested identity dimensions, publisher spoof boundaries, contextual relations and frozen freshness. |
| PostgreSQL integration | `pytest -m db`: 90 passed; the selected-product test file passes 9 tests, including the 100-requirement assessment, malformed planner terminal record, cancel-before-plan-save, terminal AI-budget skip and failed-byte accounting. The suite upgrades, downgrades and re-upgrades the schema and runs `alembic check` in isolated PostgreSQL 16.15 schemas. |
| API/frontend checks | Ruff check/format and generated API types passed; 53 Vitest tests passed; ESLint, TypeScript and Vite production build passed using the bundled Node runtime. |
| External/manual checks | Live source-class coverage, real Personal AI structured extraction, manual citation audit, browser/mobile/keyboard inspection, hosted CI and multi-instance execution were not run. The checkout has no configured Git remote. Deterministic fakes establish local contract behavior only. |

The final offline and PostgreSQL runs include the latest grounding and product-research terminal/cancellation cases. PostgreSQL requires sandbox access to the local test port: a restricted invocation failed with `Operation not permitted`, and the isolated-database invocation passed. `make validate` was not run as a wrapper because this host's bundled pnpm does not match the pinned version; every constituent deterministic check ran directly. A separate credentialed live run was unavailable. The test runs report existing Starlette/httpx and Alembic configuration deprecation warnings.

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
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test /opt/homebrew/bin/uv run pytest -m db` | Passed: 68 tests against the isolated PostgreSQL 16.15 test database. Research tests cover request replay/version gates, competing runs, ownership, bounded provider over-responses and malformed shapes, partial durability, retained result lineage, deadline expiry during database lock waits, finite error-code sanitization, cursor validation/tie ordering, run-scoped candidate paging, cancellation/deletion/restart races and planner fallback. Migration tests upgrade, downgrade and re-upgrade fresh schemas and run Alembic's model-drift check. |
| Ruff and generated API types | Passed: `ruff check`, `ruff format --check` (85 API source/test/migration files) and `scripts/generate_api_types.py --check`. |
| Frontend | Passed: 42 Vitest tests, ESLint, TypeScript project build and Vite production build using bundled Node 24.19.0. The 11 Discover tests cover validated lost-ack form restore, unknown-503 exact replay, revision-conflict refresh/new-key recovery, terminal candidate refresh without repeat invalidation, selected older-run results, candidate paging, cancellation and empty/history states. |
| Manual desktop browser smoke | Passed on local fake configuration: opened a project, submitted an explicit manual query, observed running and terminal counters, and verified the empty result state and run history. The default fake intentionally returned no search results. Mobile viewport inspection was not run. |
| Aggregate/hosted/live checks | `make validate` was not run because the installed pnpm wrapper is 11.19.0 while the project pins 10.34.6; its applicable constituents above were run directly using installed dependencies. No Tavily credential or verified external structured-task endpoint was available, so live search and live Personal AI planning remain unverified. Hosted CI and multi-instance execution were not run. |

The manual browser smoke used only fake providers. It is evidence for the route and progress/empty-state interaction, not for search quality or returned products. Discovery execution is intentionally single-process and local until the later durable-job phase.

The independent review follow-up split research commands, execution, reads and shared validation into focused modules behind the `research.service` facade. Persistence now truncates overlarge provider responses to the locked run's remaining result/candidate allowance, rejects late results after database lock waits cross the deadline, and maps unknown provider error values to a finite safe code set. Run history and candidate reads now share strict timezone-aware opaque cursors with deterministic timestamp/UUID ordering, default-20/max-100 bounds and optional run scoping; URL grouping preserves trailing path slashes. Discover pages both histories and selected-run candidates, refetches candidates when the selected run's counters/status advance, restores validated pending objective/manual-query fields after a reload, and refreshes project revision after a revision conflict. Pending command data uses tab-scoped session storage and is cleared on known pre-acceptance responses; terminal run data remains in the API. No new browser smoke was run for these follow-up interactions.

## Phase 4 completion and evidence — 2026-10-04

Phase 4 adds owner-scoped catalog products, variants, identifiers, candidate mappings, immutable retrieval observations, timestamped decimal offers, deterministic variant matching, reversible manual corrections, candidate mapping controls and product detail. The retriever rejects private destinations, validates and pins the public connection address per redirect, and caps time, redirects, decoded bytes and content types. Local extraction only accepts bounded structured product data with exact excerpts present in the retrieved text or Product JSON-LD. External structured Personal AI extraction remains unavailable because its checked contract does not publish a verified task endpoint.

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff check src tests migrations` and `ruff format --check src tests migrations` | Passed; all 100 API source/test/migration files are lint-clean and formatted. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m 'not db and not live'` | Passed: 86 tests, including 8 normalization fixture cases and 12 mocked PageRetriever security cases. |
| `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m db` | Passed: 77 PostgreSQL tests on PostgreSQL 16.15. Includes catalog version/idempotency/correction/concurrency cases, fresh migration down/up/re-up with Alembic consistency check, schema constraints and Phase 3 seeded candidate/search-lineage preservation. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run python ../../scripts/generate_api_types.py --check` | Passed; committed TypeScript contracts match FastAPI OpenAPI. |
| `cd apps/web && <bundled-node> node node_modules/vitest/vitest.mjs run` | Passed: 44 UI tests, including creation of a variant under an existing product family, provenance/offer detail and rejection of unsafe outbound URLs. |
| `cd apps/web && <bundled-node> node node_modules/eslint/bin/eslint.js .`, `node_modules/typescript/bin/tsc -b`, and `node_modules/vite/bin/vite.js build` | Passed: lint, typecheck and production build. `<bundled-node>` is `/Users/jasonkli/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`. |

The Phase 4 acceptance map is in the [implementation plan](docs/planning/phase-4-implementation-plan.md). Frontend dependencies already installed in the repository were invoked directly with the bundled Node runtime; the available pnpm wrapper version differs from the version pinned in the project, so the aggregate `make validate` target was not run for this phase. All of its applicable constituent checks above passed.

Not run: live retailer/manufacturer page retrieval, credentialed Tavily or Personal AI calls, a manual desktop/mobile browser smoke for catalog screens, hosted CI, cloud deployment and multi-instance execution. Mocked transport and local fixtures do not establish retailer access or extraction quality on current live pages. Phase 5 must reuse the guarded `PageRetriever`; it should keep source snapshots/claims distinct from catalog observations, normalized attributes and user corrections.

## Phase 4 independent-review fixes — 2026-10-04

The Phase 4 review fixes preserve conservative catalog matching and evidence, put a total deadline and pre-allocation decompression cap around retrieval, make correction history effective-state aware, require amount/currency as a pair in PostgreSQL, and complete the correction/detail variant flows. The full acceptance map and code links are in the [Phase 4 plan](docs/planning/phase-4-implementation-plan.md#independent-review-follow-up--2026-10-04).

| Check | Result |
|---|---|
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m 'not db and not live'` | Passed: 96 tests; 81 database/live tests deselected. |
| `cd apps/api && TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:55843/shopping_test UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run pytest -m db` | Passed: 80 PostgreSQL tests on isolated PostgreSQL 16. Includes raw half-known offer pair rejection, catalog authority conflicts, nested correction/revert replay and migration down/up/re-up plus Alembic consistency. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run ruff check src tests migrations` and `ruff format --check src tests migrations` | Passed. |
| `cd apps/api && UV_CACHE_DIR=/private/tmp/shopping-uv-cache /opt/homebrew/bin/uv run python ../../scripts/generate_api_types.py --check` | Passed; generated API contracts are current. |
| `cd apps/web && <bundled-node> node node_modules/vitest/vitest.mjs run` | Passed: 46 tests, including variant pagination, duplicate correction locking, lost-ack review/replay and variant-specific product detail. |
| `cd apps/web && <bundled-node> node node_modules/eslint/bin/eslint.js src tests`, `node_modules/typescript/bin/tsc --noEmit` and `node_modules/vite/bin/vite.js build` | Passed: lint, typecheck and production build. The bundled Node path is recorded in the Phase 4 evidence above. |

The first PostgreSQL invocation was blocked by the execution sandbox's loopback restriction; the same test run was executed with local database access and passed. The test database is isolated and its fixture creates/drops per-test schemas. Implementation fixes are committed in `0d7c7ae`, `6787e1b`, `a270343` and `3a7d279`; the parent session's light review remains.

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
