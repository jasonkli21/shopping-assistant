# Shopping Assistant

A personal shopping research and decision-support application focused on **search, discovery, evidence, comparison, and shortlisting** rather than checkout.

The core user journey is:

> Need → Requirements → Discovery → Research → Comparison → Shortlist

This repository is intentionally scaffolded as a **modular monolith** with a React/TypeScript SPA, a Python/FastAPI API, PostgreSQL as the application datastore, and a clean integration boundary to the separate `personal-ai-system`.

## Status

This repository is at **Phase 0: technical foundation**. Product behavior is intentionally not implemented yet. The scaffold exists to give Codex a verified starting point and to preserve the product and architectural decisions already made.

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

### 4. Start the web app

In a separate terminal from the repository root:

```bash
cd apps/web
pnpm install --frozen-lockfile
pnpm dev
```

The default frontend dev server uses strict port 5173 and talks to `http://localhost:8000`. The landing page shows API connection status and retry. `/health` is liveness, not database readiness.

Run `make validate` for lint/format/tests/typecheck/build, `make migrate` for online migrations, and `bash scripts/validate_scaffold.sh` for compilation. See [validation results and remaining checks](VALIDATION.md).

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
