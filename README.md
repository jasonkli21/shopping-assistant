# Shopping Assistant

A personal shopping research and decision-support application focused on **search, discovery, evidence, comparison, and shortlisting** rather than checkout.

The core user journey is:

> Need → Requirements → Discovery → Research → Comparison → Shortlist

This repository is intentionally scaffolded as a **modular monolith** with a React/TypeScript SPA, a Python/FastAPI API, PostgreSQL as the application datastore, and a clean integration boundary to the separate `personal-ai-system`.

## Status

**Phases 1 and 2 are complete locally:** projects, requirements, conversations, and confirmed intent proposals persist in PostgreSQL behind owner-scoped APIs. AI suggestions remain reviewable until explicitly applied. The upstream Personal AI task contract is not yet available, so local development uses a deterministic fake and live compatibility remains pending. See the [Phase 2 evidence](docs/planning/phase-2-implementation-plan.md), [API contract](docs/api/api-contract.md), and [validation record](VALIDATION.md).

## Quick start

### Prerequisites

- Python 3.12+
- `uv`
- Node.js 20+
- `pnpm` 10 (version pinned in `apps/web/package.json`)
- Docker / Docker Compose

### 1. Configure local settings

```bash
cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

The API and Alembic load repository-root `.env`; process environment variables override it. Frontend public configuration lives in `apps/web/.env.local`. Keep credentials out of `VITE_` variables.

`LOCAL_OWNER_ID` optionally selects the stable local owner; it defaults to a fixed development UUID and is never accepted from request data. This unauthenticated local mode is intended for localhost development only.

Assistant generation defaults to `PERSONAL_AI_MODE=fake` for deterministic local work. `PERSONAL_AI_MODE=external` stays unavailable until the separate Personal AI service publishes a verified structured shopping-task contract; see the [contract check](apps/api/src/shopping/integrations/personal_ai/CONTRACT.md).

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 3. Start the API

```bash
cd apps/api
uv sync --locked --extra dev
uv run alembic upgrade head
uv run uvicorn shopping.main:app --reload --host 127.0.0.1 --port 8000
```

API health endpoint:

```text
GET http://localhost:8000/health
```

The Home page at `/` creates projects; `/projects/{project_id}` opens their Overview. Project and requirement routes are listed in the [API contract](docs/api/api-contract.md). Apply database migrations before starting the API.

### 4. Start the web app

In a separate terminal from the repository root:

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

The default frontend dev server uses strict port 5173 and talks to `http://localhost:8000`. `/health` is liveness, not database readiness.

Run `make validate` for lint/format, deterministic offline tests, generated API type checking, typechecking and build. PostgreSQL integration tests are explicit: set `TEST_DATABASE_URL` to a disposable database whose name starts with `test_` or ends with `_test`/`_tests`, then run `make test-db TEST_DATABASE_URL=...`. The test fixture creates and drops isolated schemas and refuses the configured application database. CI has a separate PostgreSQL 16 job. See [validation results and remaining checks](VALIDATION.md).

## Repository map

```text
apps/api/        FastAPI backend
apps/web/        React + TypeScript frontend
packages/        Shared/generated contracts when needed
docs/            Product, architecture, API, and implementation plan
infra/           Deployment scaffolding; intentionally minimal for now
scripts/         Developer scripts
```

## Architectural rules

1. **Shopping domain state lives here.** Shopping projects, products, variants, offers, evidence, comparisons, and shortlists are shopping-app concerns.
2. **Generic intelligence lives in `personal-ai-system`.** This app integrates through an explicit client boundary rather than importing its internals.
3. **PostgreSQL is authoritative for shopping-domain data.** Do not move the domain model to Firestore merely to mirror another project.
4. **Use a modular monolith.** Keep strong internal boundaries, but do not create microservices prematurely.
5. **Evidence and provenance are first-class.** Separate source facts, observations, AI assessments, and user judgments.
6. **Do not add infrastructure without a demonstrated need.** No Redis, Celery, Kafka, Pub/Sub, Kubernetes, Elasticsearch, or vector database in the initial phases.
7. **Tests and source code remain in separate directories.**

## Start here for Codex

Read [`CODEX_HANDOFF.md`](./CODEX_HANDOFF.md), then the docs in this order:

1. `docs/product/product-vision.md`
2. `docs/product/ux-design.md`
3. `docs/architecture/architecture.md`
4. `docs/architecture/data-model.md`
5. `docs/architecture/ai-search.md`
6. `docs/architecture/personal-ai-integration.md`
7. [Implementation plans index](docs/planning/implementation-plans-index.md) and selected phase plan
8. `docs/api/api-contract.md`
9. Remaining `docs/architecture/*.md`, `docs/adr/*.md`, and `docs/product/roadmap.md`

The Phase 0 review/corrections are complete; external verification gaps are recorded in `VALIDATION.md`. Execute only the explicitly selected phase and stop. Phase 6 requires a comprehensive repo-wide review before Phase 7.
