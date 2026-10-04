# Phase 1 — Shopping projects and editable requirements

Status: planned. Requires the corrected Phase 0 code and review of its verification gaps. Apply [shared contracts](implementation-plans-index.md). Primary references: product vision, UX Overview/Home, data model, API draft and ADRs 0001–0002.

## Outcome, slice and boundary

A user creates “Vacuum for apartment,” sets a USD 400 maximum, adds an editable must-have about pet hair, reloads and sees the same state. A second browser tab cannot silently overwrite newer edits. This durable manual slice precedes AI complexity.

In scope: project create/list/read/update/archive/delete, goal/category/notes, budget, requirements, Home/recent projects and Project Overview. Out of scope: assistant proposals, conversation, search, candidates, catalog, offers, evidence, comparisons, persistent preference learning or cloud authentication.

## Contracts and affected modules

Implement `projects/{models,schemas,repository,service,router}.py` (combine small files where clearer), `api/router.py`, database model registration/session dependency, and web `features/projects/`, routing and API types. Keep ORM and transport models distinct. Generate committed TypeScript transport types from FastAPI OpenAPI with a reproducible script once these contracts exist; `packages/api-types/` is the home for generated contracts, not a hand-maintained duplicate domain model.

Tables:

- `shopping_projects`: UUID PK, `owner_id` UUID, title (1–200 trimmed characters), goal (1–4000), nullable category (≤100), status `active|completed|archived`, nullable budget target/maximum `NUMERIC(14,2)` and currency (three uppercase letters; supported-code validation), notes (≤10000), revision ≥1, created/updated UTC times, nullable deleted_at. Require currency iff either budget is present; nonnegative amounts, target ≤ maximum when both provided. Null clears a field; omitted PATCH fields are untouched.
- `project_requirements`: UUID PK, project FK, kind `must_have|preference|constraint`, label (1–300), detail (≤2000), optional attribute_key, operator `eq|gte|lte|contains|one_of`, bounded JSONB value and nullable unit, integer position, origin `user|ai_confirmed`, timestamps. Typed criteria are optional: a text-only requirement remains usable. Validate operator/value shape and units, but avoid a category-wide attribute ontology. Reject duplicate IDs, not equal prose; two differently qualified requirements can look similar.

Add indexed owner/update ordering and project/position lookup. Use FK constraints and budget checks in PostgreSQL as well as schemas. The stable local principal comes from server settings/dependency; no user table or client-controlled owner yet. Every repository read and mutation checks owner/project scope. Project DELETE tombstones the project, hides it and makes nested operations unavailable; archive is a reversible status. Physical purge/export belongs to Phase 9.

Endpoints follow the Phase 1 API draft. Create returns 201 and full project; list returns items/cursor. Detail includes ordered requirements. Requirement commands return updated project revision. Updates/deletes use `expected_version`; deleting a missing/foreign requirement returns 404. The transaction locks/checks project revision, validates all changes, updates requirements and increments once. Status updates and reordering preserve IDs. No AI changes arrive in this phase.

Use synchronous SQLAlchemy sessions and sync endpoints/services for database work. Later async provider operations acquire short sessions outside I/O or run sync services through a threadpool; do not put blocking queries into the async event loop. Close sessions, roll back exceptions, and never depend on a singleton session. Import all implemented models into Alembic metadata explicitly.

## Ordered work packages

### 1A — Persistence and database test foundation

Create the first migration with only these two tables, constraints and indexes. Add local principal, session dependency and repositories. Build a disposable PostgreSQL fixture using `TEST_DATABASE_URL`, register `db`/`live` markers, guard against known application databases, and isolate tests via transactions or per-test schema with explicit cleanup. Use `tests/db/`, `tests/projects/`, not `src/` fixtures. Add PostgreSQL 16 service to a separate CI database job; set the ordinary backend CI job and `make test` to `uv run pytest -m 'not db and not live'`, with database tests run explicitly in their provisioned job. Default unit/provider tests remain network-free; missing TEST_DATABASE_URL in an explicitly requested database run fails clearly.

Test fresh migration, upgrade/downgrade on disposable data, JSONB/decimal/UTC roundtrip, budget constraints, owner filtering, missing references, rollback and concurrent revision checks. No empty general-purpose repository superclass.

### 1B — Service and API vertical slice

Implement create/read/list/patch, requirements and tombstone semantics with typed schemas and error envelope. Include deterministic pagination tie-breaking by updated_at and ID. Use unknown fields rejection for commands. Test omission versus null, invalid currency/value shapes, oversized input, ordering, duplicate writes from stale tabs, and no mutations on failed validation. Generate types and check reproducibility in CI; test representative OpenAPI request/response payloads.

### 1C — Home and Overview UI

Add routes `/` and `/projects/:projectId`; Home creates projects with manual intent/goal and shows recents/empty state. Overview edits title, goal, notes, budget, status and ordered requirements using TanStack Query. Forms keep unsaved edits after network failure and surface field errors. On 409, show that the project changed, refetch and let the user reconcile; never auto-resubmit stale edits. Confirm delete in the UI and distinguish it from archive. Hide candidate/research counts until their phases exist.

Include accessible labels, keyboard focus after create/delete, save-pending state, disabled duplicate submission, missing/deleted project screen, retryable load error and narrow-mobile single-column layout. No assistant placeholder that implies AI is working.

### 1D — Completion review and handoff

Exercise create → edit → requirement reorder → reload → archive/restore → delete. Document the local owner and update API draft/generated types, migration/model inventory and phase evidence. Suggested commits: persistence/test harness; API/types; UI/interaction tests; acceptance/documentation.

## Acceptance and verification

- The concrete apartment/vacuum slice survives reload/API restart in PostgreSQL.
- Precise budgets, omitted/null updates and text/structured requirements roundtrip without loss.
- Stale project and nested requirement writes return 409 with no partial update; different owners cannot read or mutate the project.
- Deleted projects vanish from lists and nested operations; archived projects remain restorable.
- UI loading/error/empty/mobile/edit-conflict states have assertions and a manual keyboard/viewport check.
- Fresh and upgrade migrations, rollback and metadata checks pass against PostgreSQL 16; offline/default tests make no external calls.

Run `make validate`, `uv run pytest -m 'not db and not live'`, `TEST_DATABASE_URL=... uv run pytest -m db`, `make migrate`, and `uv run alembic check` (API directory where applicable). On a disposable DB run upgrade → downgrade base → upgrade; never downgrade a developer database with useful data. Run the new OpenAPI generation/check command and record its exact spelling. Browser smoke is manual until Phase 6 E2E; CI credentials/cloud are not required.

Completion questions: Can transport models diverge from ORM without accidental leaks? Are owners checked on nested resources? Can two tabs corrupt requirements? Is manual entry pleasant without AI? Does the migration import all models? Did the phase avoid catalog/assistant infrastructure?

Handoff: durable project IDs/revisions, validated requirement/budget shapes, ownership dependency, service transaction boundary, generated API types and PostgreSQL test harness. Phase 2 may propose changes through these services only. No unresolved external provider decision blocks this phase.
