# Architecture

## Architectural style

Use a **modular monolith**: one frontend application, one backend deployment, one PostgreSQL domain datastore, and strongly separated internal modules.

Do not create microservices merely because domain modules have names like `catalog` or `research`.

## System boundary

```text
                         personal-ai-system
                    generic AI + memory platform
                               │
                               │ typed HTTP client
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                     Shopping Assistant                      │
│                                                              │
│ Project │ Catalog │ Research │ Search │ Extraction │ Evidence│
│ Compare │ Prefs   │ Conversations │ Integrations            │
└───────────────────────┬───────────────────────┬──────────────┘
                        │                       │
                        ▼                       ▼
                  PostgreSQL               External web/search
```

## Shopping-app responsibilities

- shopping projects and requirements;
- canonical products and variants;
- retailer offers;
- shopping-specific research planning;
- source/claim/evidence representation;
- project-relative assessments;
- comparisons and shortlist;
- shopping preferences;
- shopping UX and APIs.

## Personal-AI responsibilities

- model/provider access;
- generic AI generation/streaming;
- generic user-wide memory;
- reusable model orchestration primitives;
- possibly generic research capabilities in the future.

The shopping app must not import internal personal-AI packages. Integrate over an explicit API/client boundary.

## Backend modules

```text
projects/       project lifecycle and requirements
catalog/        products, variants, attributes, offers
research/       research runs, planning, orchestration, jobs
search/         search provider abstractions/adapters
extraction/     retrieval and structured extraction
evidence/      sources, claims, provenance, assessments
comparisons/    project-relative comparison state
preferences/    project and persistent shopping preferences
conversations/  project-aware conversational state
integrations/   external system adapters
db/            database foundation
api/           HTTP routing and transport schemas
```

Modules may call each other through explicit services/repositories. Avoid circular dependencies and generic dumping-ground utility modules.

## Frontend organization

Prefer feature-oriented organization:

```text
features/projects/
features/discovery/
features/products/
features/comparisons/
features/shortlist/
features/assistant/
```

Shared presentational primitives belong in `components/ui/`.

## Provider boundaries

Infrastructure dependencies remain swappable:

- `PersonalAIClient`
- `SearchProvider`
- `PageRetriever`
- `ResearchExecutor`

Domain code should depend on interfaces/protocols rather than vendor SDKs.

## Execution model

Early phases run synchronously/in-process where practical. Research work is modeled as persistent runs/jobs so execution can later move to Cloud Run Jobs without rewriting domain semantics.

Research execution now submits persisted run IDs through the `ResearchExecutor` boundary and records durable jobs, attempts, and leases. The current in-process executor and manual runner share the same ID-based claim path; remote dispatch remains conditional on measured need. See the [research execution decision](research-execution-decision.md), [module guide](../../apps/api/src/shopping/research/README.md), and [implementation plans](../planning/implementation-plans-index.md).
