# Phase 6 — Decision workspace and MVP review gate

Status: planned. Requires completed Phases 1–5 and their honest external verification record. Read the [index](implementation-plans-index.md), complete product/UX/API docs and all architecture/ADRs. This is the major product and repository review gate, not merely another feature increment.

## Outcome and scope

The user completes Need → Requirements → Discovery → Research → Comparison → Shortlist in one durable project, understands uncertainty and can resume after restart. Smallest decision slice: two researched variants → meaningful-difference comparison → note/shortlist one/reject the other → reload and inspect the rationale/evidence. Then validate the full journey from Home.

Scope: shortlist/rejections, notes, saved comparisons and dimensions, favorite/purchased user state, assistant-supported project refinements and comprehensive review. Exclude checkout, automatic purchase, receipts/warranty/price alerts, collaboration, persistent preference learning, autonomous re-research loops, remote orchestration and cloud launch.

## Domain and persistence contracts

Use exact `ProjectProduct`/variant identity for decisions; product-family grouping is presentation only. Implement decision services in `projects/` (a focused `decisions.py` is sufficient), saved comparison services in `comparisons/`, catalog-private favorites in `catalog/`, assistant operation extensions in `conversations/`. Evidence supplies grounded view data through its service; comparison must not call providers directly.

Add:

- `project_product_decisions`: one current row per ProjectProduct, state `considering|shortlisted|rejected|purchased`, reason text, controlled rejection reasons (`too_expensive|missing_feature|too_large|appearance|weak_evidence|wrong_category|already_owned|other`), concerns, selected offer observation ID if any, actor/origin and timestamps. This single state avoids contradictory shortlist/rejection tables; shortlist/rejection endpoints are projections/commands over it. Preserve prior transitions in a compact `decision_events` audit. Purchased is a manual judgment, not proof of payment. Favorite is independent.
- `user_notes`: project and nullable ProjectProduct, owner, bounded text (≤10000), created/updated and version. No notes in canonical fact/claim payloads; use project revision for transactional editing.
- `saved_products`: owner/variant unique, favorite flag and timestamps; owned/purchased context stays the explicit project decision initially. Do not infer ownership globally or promote a preference.
- `comparisons`: project, title, ordered ProjectProduct IDs (2–6), ordered dimension definitions, display mode `all|differences`, project revision and comparison revision, immutable generated view snapshot references/time. Prefer relational `comparison_items`/`comparison_dimensions` with FKs/order if JSONB membership cannot enforce reference integrity. Dimensions have key/label/unit and type `fact|offer|evidence|project_fit|user_note`; custom label is bounded, no arbitrary code/formula. When creating/updating a comparison in a context transaction, snapshot records the committed project revision so it is not instantly stale. Snapshot includes canonical/assessment revisions, claim/snapshot IDs and offer observation IDs for each cell, plus unknown/conflict/stale status.

Comparison rules: normalize equivalent units only with deterministic conversions; unequal currencies are not directly ranked; “unknown” cannot mean equal; variant differences and offer observation dates remain visible. Evidence dimensions compare qualified claims, not unqualified marketing text. Difference-only mode hides demonstrably equal comparable values, never unknown/conflicting values. Opaque numeric universal ranking is prohibited. New requirements/offers/evidence mark snapshot stale; regeneration creates a new version rather than silently rewriting the user's saved comparison.

Commands lock project/context, validate owner/membership/offer variant, apply state and increment project revision atomically. Rejection removes current shortlist membership by replacing state; undo restores considering unless an explicit prior state is requested. Shortlisting clears current rejection but retains event history. Purchased cannot simultaneously be rejected. Deleting project hides private decisions/notes/comparisons; canonical observations remain until authorized purge. Favorite commands are owner/version scoped and independent of project revisions when no project context is changed.

API follows shortlist/rejection/comparison draft, refining path IDs to ProjectProduct IDs (document the change). Add notes CRUD, favorite command and explicit purchased/undo command. Comparison create/update accepts expected_version and validates all selected variants belong to the project; comparison edits carry expected_comparison_version too. Repeated command request keys prevent duplicate decision events where assistant/command replay is possible. `GET` never mutates decisions or regenerates comparisons.

## Assistant behavior and UX

Extend the Phase 2 proposal schema by explicit task version to whitelisted `shortlist|reject|add_note|set_comparison_dimensions|refine_requirements` operations with exact scoped IDs. Assistant can answer using bounded current claims/assessment citations. “Compare these,” “only meaningful differences,” “add warranty,” and “ignore aesthetics” become inspectable comparison/requirement proposals. Unknown warranty becomes an unknown dimension; no made-up research. User confirmation applies durable mutations. Research launches require an explicit user action/proposal confirmation and the existing bounded research command; no hidden automatic spending loop.

Desktop workspace has Overview/Discover/Compare/Shortlist/Research with collapsible assistant; mobile uses focused screens and assistant drawer. Product cards expose shortlist/reject and reason selection. Shortlist shows rationale/concerns/notes/observed offers. Product detail exposes favorite/manual purchased state. Saved Products is lightweight and scoped to user's favorites. Compare has selectable dimensions, difference toggle and source inspection for every material assertion. At 320px use horizontal scroll with accessible headers or stacked per-dimension cells; do not shrink unreadable text.

Loading states keep previous decision data; optimistic updates only with rollback/refetch and explicit revision conflicts. Empty shortlist/comparison selection explains the next action. Failed save preserves notes and selected dimensions. Missing/deleted/mismatched variants, stale comparison and no-offer/unknown-claim cells are explicit. Keyboard controls and evidence panels preserve focus. Outbound retailer links are informational, no checkout.

## Ordered work packages

### 6A — Decisions, notes and favorite/purchased state

Migrate minimal tables/services and implement scoped transactional commands. Test shortlist→reject→undo, purchased/rejected exclusion, favorite independence, wrong-offer variant, duplicate command replay, concurrent edits, note persistence and tombstone behavior. Keep user state separate from canonical attributes and claims.

### 6B — Comparison domain and snapshot APIs

Persist membership/dimensions, deterministic cell construction and evidence-linked snapshots. Test unit conversion, currency mismatch, unknown versus equal, stale requirement/catalog/evidence/offer revisions, variant changes and source IDs. A saved view is reproducible from snapshot provenance; regeneration is explicit.

### 6C — Complete decision workspace

Wire feature routes, shortlist/reject reason flows, notes/favorites/purchased and comparison screens. Product/detail/discovery state remains synchronized through Query invalidation. Test mobile, failed optimistic writes, conflict recovery, empty states and citation navigation.

### 6D — Conversational refinements

Extend schemas/prompts/fakes/evals for decision commands and comparison dimensions. Reuse proposals/application service; forbid arbitrary identifiers/actions and unsupported evidence. Test multi-operation atomicity and stale previews. A conversational requirement change flags old research context without deleting candidates or silently regenerating results.

### 6E — MVP journey tests and product review

Add a small browser E2E suite under `apps/web/tests/e2e/` (browser tooling is justified for application testing, not web research). Add/document `pnpm test:e2e` with API, disposable PostgreSQL and deterministic provider selection; exclude E2E files from Vitest unit collection. Fixture journey: create intent/project → confirm requirements → discover → normalize → research → inspect conflicts → compare differences → shortlist/reject/note → restart/reload. Include provider failure/recovery and stale proposal/comparison scenarios. Choose two categories to expose hardcoded assumptions: vacuum and chair/monitor. Review actual UI usability and source inspection, not just DOM selectors.

### 6F — Mandatory repository-wide gate

Create `docs/planning/phase-6-review.md` with findings, severity, concrete files/behavior, fixes/tests and remaining external checks. Review all code/docs, module dependency direction/cycles, source/test separation, readability, unnecessary abstractions/infrastructure, transaction/ownership integrity, migration path, prompt/schema failures, provenance/entity identity, budget enforcement, SSE lifecycle, retrieval security, private logging and mobile/accessibility. Compare actual behavior to product vision, UX, API draft, ADRs and all Phase 1–6 acceptance criteria.

Resolve all data-loss, authorization, provenance, cost-bound and core-journey blockers before declaring the gate passed. Other findings need an explicit disposition, scope/owner and successor reference. Demonstrate each major invariant with code/test evidence, not a checklist of “reviewed.” No Phase 7 work begins until this report and the phase evidence show the gate passed. Credentialed coverage may remain clearly documented; if absent, label the MVP offline-verified and require live research audit before production, without claiming live product quality passed.

## Acceptance, verification and handoff

Full journey is durable and testable with deterministic providers; every selected item is a precise variant. Conflicting state transitions are impossible, notes/favorites/purchased persist, comparison unknowns and citations remain honest, assistant changes are explicit and safe, and restart resumes saved workspace without duplicate work. Repo-wide gate has no unresolved blocker and covers architecture/code/product/security as above.

Run `make validate`, PostgreSQL decision/comparison/migration tests, OpenAPI/types check, offline command/evidence evals and new `pnpm test:e2e`. Upgrade seeded Phase 5 data and `alembic check`. Manually inspect keyboard and 320px/desktop journey, slow/failed API, citations and outbound links. Separately audit one live end-to-end discovery/research journey if providers are available; record exact results and gaps. Deployed checks wait for Phase 9.

Suggested commits: decisions/notes; comparisons/snapshots; workspace UI; proposal commands; E2E journey; gate fixes/review evidence (split fixes by concern). Completion questions: Can a user make an informed decision from the whole journey? Does every asserted cell have provenance? Do state edits preserve work? Are variants/offer dates visible? Is the repository still a coherent modular monolith? Are gate findings actually resolved?

Handoff: complete MVP contract, reproducible journey fixtures, comparison/decision invariants, reviewed dependency map, performance/budget measurements and mandatory gate report. Phase 7 is authorized only after the gate. No automatic preference promotion, cloud/auth claims or background execution need is implied.
