# Shopping Assistant

A personal shopping research and decision-support application for going from a vague need to an evidence-backed shortlist.

The application focuses on the hard part of shopping—understanding requirements, discovering products, researching evidence, comparing tradeoffs, and deciding what is worth considering—rather than checkout or order management.

## What it does

The central artifact is a durable **Shopping Project**.

A project can contain:

- a shopping goal and intent;
- editable requirements and budget;
- project-aware conversation history;
- bounded discovery and research runs;
- source/search lineage;
- normalized products, variants, and offers;
- product evidence and source-backed claims;
- project-relative assessments;
- side-by-side comparisons;
- explicit decisions, shortlist, and rejection state;
- user notes and corrections.

The core user journey is:

```text
Need -> Requirements -> Discovery -> Research -> Comparison -> Shortlist
```

Examples:

- “I need a chair for my apartment.”
- “Find a cordless vacuum under $400.”
- “What is like this product, but cheaper?”
- “Compare these three monitors.”
- “Teach me what matters when buying an air purifier.”

## Product principles

- **Start from intent, not just keywords.**
- **AI inference does not silently become durable truth.**
- **Explain tradeoffs instead of producing opaque universal scores.**
- **Separate source facts, observations, AI assessments, and user judgment.**
- **Preserve evidence and provenance.**
- **Research should refine a durable project rather than reset on every query.**
- **The product stops at shortlist rather than checkout.**
- **Persistent preferences should be promoted deliberately.**

## Architecture

```text
                     personal-ai-system
                 generic AI / memory layer
                           |
                           | typed HTTP
                           v
 +------------------------------------------------------+
 |                  Shopping Assistant                  |
 |                                                      |
 | projects       catalog        research               |
 | search         extraction     evidence               |
 | comparisons    preferences    conversations          |
 | integrations                                         |
 +---------------------+----------------------+----------+
                       |                      |
                       v                      v
                 PostgreSQL             search / web
```

The application is a modular monolith: one frontend, one backend deployment, one authoritative PostgreSQL datastore, and explicit internal module boundaries.

## Ownership boundaries

**Shopping Assistant owns:**

- shopping projects and requirements;
- products, variants, and offers;
- research runs;
- shopping evidence/claims;
- comparison state;
- shortlists/rejections;
- shopping-specific preferences;
- shopping UI and API behavior.

**`personal-ai-system` owns reusable intelligence:**

- model/provider access;
- generic generation;
- user-wide memory;
- generic research/orchestration primitives.

The shopping app integrates over explicit contracts rather than importing AI-system internals.

## Repository layout

```text
.
├── apps/
│   ├── api/                # FastAPI backend
│   └── web/                # React + Vite frontend
├── packages/               # shared/generated contracts where needed
├── docs/
│   ├── product/            # product vision and UX
│   ├── architecture/       # architecture, data model, AI/search contracts
│   ├── api/                # API contract
│   └── planning/           # detailed engineering plans/history
├── infra/
│   ├── local/
│   └── cloud/              # Cloud Run/Firebase deployment inputs and scripts
├── scripts/
├── docker-compose.yml
└── Makefile
```

## Tech stack

### Web

- React 19
- TypeScript
- Vite
- React Router
- TanStack Query
- pnpm 10.34.6

### API

- Python 3.12+
- FastAPI
- SQLAlchemy 2
- Alembic
- PostgreSQL / psycopg
- HTTPX

### Providers

- deterministic/fake local assistant and search modes by default;
- optional Tavily search adapter;
- explicit `personal-ai-system` integration boundary.

## Local setup

### Prerequisites

- Python 3.12+
- `uv`
- Node.js 20+
- pnpm 10.34.6
- Docker / Docker Compose

### 1. Clone and configure

```bash
git clone https://github.com/jasonkli21/shopping-assistant.git
cd shopping-assistant

cp .env.example .env
cp apps/web/.env.example apps/web/.env.local
```

The local defaults are intentionally deterministic:

```env
ENVIRONMENT=local
PERSONAL_AI_MODE=fake
SEARCH_PROVIDER=fake
```

No external model/search credentials are required for the default local workflow.

### 2. Start PostgreSQL

```bash
docker compose up -d postgres
```

### 3. Start the API

```bash
cd apps/api

uv sync --locked --extra dev
uv run alembic upgrade head
uv run uvicorn shopping.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8000
```

Health endpoint:

```text
GET http://localhost:8000/health
```

### 4. Start the web app

In another terminal:

```bash
cd apps/web

corepack enable
corepack prepare pnpm@10.34.6 --activate
pnpm install --frozen-lockfile
pnpm dev
```

The Vite development server uses port `5173` and talks to the API at `http://localhost:8000`.

Open:

```text
http://localhost:5173
```

## Optional provider configuration

### Tavily search

Local search defaults to the fake provider.

To opt into Tavily:

```env
SEARCH_PROVIDER=tavily
TAVILY_API_KEY=...
```

There is no silent fallback to fake data when a live provider is selected.

### `personal-ai-system`

Local assistant generation defaults to:

```env
PERSONAL_AI_MODE=fake
```

External integration uses:

```env
PERSONAL_AI_MODE=external
PERSONAL_AI_URL=http://localhost:8080
```

Only enable this when the upstream structured shopping contract and identity/data-handling boundary are configured.

## Research bounds

The search/research pipeline is deliberately bounded.

Example controls include:

```env
RESEARCH_MAX_QUERIES=8
RESEARCH_MAX_CANDIDATES=20
RESEARCH_MAX_RESULTS=60
RESEARCH_DEADLINE_SECONDS=60
RESEARCH_PROVIDER_TIMEOUT_SECONDS=15
RESEARCH_MAX_CONCURRENT_SEARCHES=1
RESEARCH_MAX_CONCURRENT_RUNS=2
```

These controls keep provider usage and request execution predictable.

## Development checks

Run the repository validation suite:

```bash
make validate
```

It covers linting/formatting, deterministic offline tests, generated API type checks, TypeScript checks, and the production web build.

PostgreSQL integration tests are opt-in and require a disposable database:

```bash
make test-db TEST_DATABASE_URL=postgresql+psycopg://...
```

The test harness rejects the configured application database and requires an explicitly test-named database.

## Cloud deployment

The intended cloud direction is:

```text
Browser
   |
   v
Web frontend
   |
   v
Cloud Run: Shopping API
   |
   +-------> Neon Postgres
   |
   +-------> external search/providers
   |
   +-------> personal-ai-system
```

Phase 9 now includes a local deployment foundation: locked non-root API container, Firebase Hosting configuration, authenticated owner binding, migration/backup scripts, and a deployment runbook. No account-specific resources are configured, and no cloud deployment or recovery has been verified. See [`docs/deployment/runbook.md`](docs/deployment/runbook.md) and [`docs/current-state.md`](docs/current-state.md).

A future cloud deployment should preserve these constraints:

- PostgreSQL remains authoritative for shopping-domain data;
- server/provider credentials stay out of browser-visible variables;
- production identity is verified at the API boundary;
- provider calls remain bounded and auditable;
- migrations are explicit rather than run independently by every replica;
- shopping data and AI-platform data remain separate ownership domains.

## Security and data-handling notes

- local owner identity is for localhost development only;
- browser-visible `VITE_` variables must not contain credentials;
- external provider calls are explicit and opt-in;
- source facts and AI assessments remain distinguishable;
- evidence and provenance are stored as first-class data;
- catalog corrections remain reversible;
- live providers should not silently fall back to synthetic results;
- no checkout, payment, or automated purchasing functionality is part of the application.

## Documentation

For a fresh task, use [`AGENTS.md`](AGENTS.md) for the durable repository contract and [`docs/README.md`](docs/README.md) to find the relevant documentation. [`docs/current-state.md`](docs/current-state.md) is the live implementation-status summary; verification details remain in `VALIDATION.md` and phase review records.

Human-facing product and architecture references include:

```text
docs/product/product-vision.md
docs/product/ux-design.md
docs/architecture/architecture.md
docs/architecture/data-model.md
docs/architecture/ai-search.md
docs/architecture/personal-ai-integration.md
docs/api/api-contract.md
```

## License

No license is currently specified. Add an explicit `LICENSE` file before treating the repository as generally reusable open-source software.
