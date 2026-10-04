# Phased Implementation Roadmap

Detailed execution contracts and work packages are in [the Phase 0–9 plans index](implementation-plans-index.md). This document is the summary roadmap; the selected detailed plan and index govern implementation. Phase 0 foundation and Phase 1 project workflows are implemented; validation evidence and remaining checks are in [VALIDATION.md](../../VALIDATION.md). Phases 2–9 are planned, not implemented.

Phases 0–3 are implemented and locally validated. Implement remaining phases in order; complete and review each phase before starting the next. Do not pull later infrastructure forward without a demonstrated need.

## Phase 0 — Repository and technical foundation

### Goal

Establish a clean, runnable development environment without substantive shopping features.

### Scope

- React/Vite app;
- FastAPI app;
- PostgreSQL Docker environment;
- SQLAlchemy/Alembic foundation;
- typed settings;
- frontend/backend health connectivity;
- lint/test/typecheck tooling;
- CI foundation;
- boundary protocols: `PersonalAIClient`, `SearchProvider`, `PageRetriever`, `ResearchExecutor`;
- fake providers where useful.

### Exit criteria

- local database starts;
- API health endpoint works;
- frontend starts;
- tests/lint/typecheck are runnable;
- repository structure matches architecture docs;
- no meaningful shopping feature implementation yet.

The corrected scaffold and completed checks are recorded in [Phase 0](phase-0-implementation-plan.md). Follow up only remaining verification gaps; do not recreate completed foundation work.

---

## Phase 1 — Shopping projects and requirements

Status: implemented and locally validated. See [Phase 1 acceptance evidence](phase-1-implementation-plan.md).

### Goal

Build the persistent shopping-project domain without AI.

### Scope

- `ShoppingProject`;
- project status;
- budget;
- editable `ProjectRequirement`;
- notes;
- repositories/services/migrations;
- Home and Project Overview UI;
- create/read/update project APIs.

### Exit criteria

A user can create a project and manually manage its goal, budget, and requirements through the UI.

---

## Phase 2 — AI-assisted intent and conversation

### Goal

Turn natural-language shopping intent into inspectable structured project state.

### Scope

- conversations/messages;
- concrete `PersonalAIClient` adapter or compatible development adapter;
- intent interpretation;
- requirement proposals/updates;
- separate conversational text from structured mutations;
- SSE response streaming;
- tests/evals for structured intent.

### Exit criteria

A message such as “I need a lightweight vacuum under $400 that is good with hair” can create or update editable structured requirements without parsing prose.

---

## Phase 3 — Live product discovery

Status: implemented on the deterministic local path; see [Phase 3 evidence](phase-3-implementation-plan.md). Live Tavily credentials/query quality and structured Personal AI planning remain unverified.

### Goal

Find real product candidates from the web.

### Scope

- `ResearchRun` and status;
- `SearchQuery`/search-result representation;
- Tavily `SearchProvider` adapter;
- query generation;
- bounded research budgets;
- provisional candidate extraction with search lineage (canonical products arrive in Phase 4);
- Discover UI and research progress.

### Exit criteria

A project can run live discovery and display plausible product candidates with source/discovery context.

---

## Phase 4 — Product catalog and entity normalization

### Goal

Represent products canonically instead of treating every URL as a distinct item.

### Scope

- Product;
- normalized brand identity fields (a separate Brand table only if justified);
- ProductVariant;
- bounded JSONB attributes with provenance (separate attribute tables only if justified);
- RetailOffer;
- project-product relationship;
- entity matching/deduplication;
- variant handling;
- offer extraction;
- manual correction path.

### Exit criteria

Multiple URLs/offers can resolve to one appropriate canonical product/variant while preserving retailer-specific offers.

---

## Phase 5 — Research and evidence

### Goal

Make product research explainable and source-backed.

### Scope

- sources and source metadata;
- page retrieval;
- structured claims/evidence;
- evidence/source categories;
- product assessments;
- uncertainty/conflict representation;
- product-detail research UI;
- evidence/source inspection.

### Exit criteria

A promising product can be researched across multiple sources and shown with facts, observations, assessments, provenance, and uncertainty kept distinct.

---

## Phase 6 — Decision workspace (MVP cutoff)

### Goal

Complete the end-to-end shopping decision workflow.

### Scope

- shortlist;
- rejection/reasons;
- saved comparisons;
- project-relative assessment;
- user notes;
- favorite/purchased state;
- project-aware conversational commands for filtering/refinement;
- difference-focused comparison UI.

### Exit criteria

The complete flow works:

> Need → Requirements → Discovery → Research → Comparison → Shortlist

### Mandatory review gate

Before Phase 7, perform a repo-wide review covering:

- alignment with product/architecture docs;
- implementation gaps;
- bugs/edge cases;
- modularity and dependency direction;
- code readability/comments;
- source/test directory hygiene;
- data integrity/migrations;
- AI structured-output robustness;
- research correctness/provenance;
- security and privacy basics;
- unnecessary complexity.

Fix review findings before continuing.

---

## Phase 7 — Research quality and orchestration

### Goal

Improve depth and reliability based on observed product needs.

### Possible scope

- quick vs deep research modes;
- richer research plans;
- source targeting;
- research refresh/staleness;
- retries/failure semantics;
- explicit research-job states;
- `CloudRunJobExecutor` only if real runs justify background execution.

Do not introduce queue/distributed infrastructure by default.

---

## Phase 8 — Personalization and memory

### Goal

Learn useful shopping preferences while preserving project-vs-global boundaries.

### Scope

- shopping profile;
- persistent preferences;
- preference candidates;
- explicit promotion from project state;
- personal-AI memory retrieval/proposal integration where appropriate;
- preference provenance and editability.

### Exit criteria

Cross-project preference reuse works without silently turning one-off constraints into permanent memory.

---

## Phase 9 — Cloud deployment and production hardening

### Goal

Deploy the proven local application safely and cheaply.

### Target

- web: Firebase Hosting;
- API: Cloud Run;
- DB: Neon PostgreSQL;
- secrets: Secret Manager;
- authentication: Firebase Auth / explicit single-user authorization;
- personal-AI: deployed API boundary.

### Hardening

- CORS/auth;
- schema migration discipline;
- structured logging;
- usage/research metrics;
- provider error handling;
- backups/export strategy;
- health/readiness;
- bounded Cloud Run scaling;
- provider quotas and research budgets;
- billing alerts.

---

## Phase 10+ — Optional roadmap

Only after the previous phases are stable:

- price history/alerts;
- browser extension/share sheet;
- image/visual discovery;
- email purchase extraction;
- ownership and warranty tracking;
- new-model detection;
- automated research refresh;
- cross-application travel/finance integrations;
- collaborative lists/projects.
