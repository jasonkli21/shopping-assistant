# Phase 6 independent review handoff

Reviewed 2026-10-05 at `f39b978`, covering `bd54f86^..HEAD`: API persistence (`bd54f86`), assistant proposals (`29a75a9`), workspace UI (`208dafb`), and review/docs (`f39b978`).

**At review time, the implementation was not sound enough to pass the Phase 6 gate.** The existing review's claim of no remaining code blockers was contradicted by the findings below. No substantive fixes had been implemented at `f39b978`; this handoff was the only retained change at that point. Continue Phase 6 only; do not start Phase 7. This document is the review input and disposition record.

The sequencing recommendation above is historical and was later superseded by explicit user authorization for Phase 7 and Phase 8 work. That authorization did not pass or waive the Phase 6 gate. See [`../current-state.md`](../current-state.md) for current status. Findings below remain review evidence, not standalone authorization for phase work.

Review basis: the Phase 6 plan (including its original contract), product vision/UX, architecture/ADRs, API contract, changed code/tests/migration, and the existing catalog, evidence, project, conversation, and frontend integration points. P1 means resolve before the MVP gate; P2 means a real functional issue requiring a fix or explicit gate disposition. No P0 found. Findings are grouped by behavior rather than capped.

1. **P1 — Confirmation UI omits every new assistant operation.**
   **Files:** `apps/web/src/features/assistant/ProposalCard.tsx:20`; backend `conversations/proposals.py:78`.
   **Wrong/why:** ProposalCard renders only `project_updates` and `requirement_operations`. Phase 6 mutations are in `decision_operations`, so shortlist/reject/note/comparison-only proposals show an empty diff with an enabled Apply button; mixed proposals conceal those mutations. Assistant prose is not an authoritative preview of exact persisted changes.
   **Fix/validate:** Render all supported operations with exact variant/target, state/reason/concerns, note text and replacement semantics, and comparison membership/dimensions/mode. Reject unsupported previews rather than enabling blind application. Test each operation, mixed operations, and a misleading/omissive assistant message; nothing durable changes before confirmation.

2. **P1 — PATCHing comparison dimensions crashes.**
   **Files:** `apps/api/src/shopping/comparisons/service.py:150` (`update_comparison`, `_validate_dimensions`, `_replace_dimensions`, `_build_view`).
   **Wrong/why:** `command.model_dump()` recursively converts dimensions to dictionaries. The selected `changes['dimensions']` is then consumed through `.dimension_type`, `.key`, etc. A valid dimensions edit raises `AttributeError`, producing a server error instead of a saved comparison.
   **Fix/validate:** Preserve typed dimension inputs or explicitly reconstruct them before service use. Exercise actual PATCH requests for dimensions alone and with membership/title/mode; verify ordered persistence, committed revisions, snapshot provenance, rollback on invalid references, and no 500.

3. **P1 — Differences mode claims equality without establishing it.**
   **Files:** `apps/api/src/shopping/comparisons/service.py:438`, `:493`, `:596`; evidence assessment integration.
   **Wrong/why:** Evidence equality uses only normalized value and qualifiers. Two different textual assertions with `normalized_value=None` and identical qualifiers become equal known cells and disappear. This is a normal supported claim shape, not malformed data. Evidence category is also omitted, so a manufacturer claim and a measured result can be treated alike. Project-fit `mixed` conclusions are labeled known and equal solely by the word `mixed`, hiding unresolved disagreement.
   **Fix/validate:** Hide only demonstrably comparable, equivalent qualified evidence; unnormalized claims must remain visible unless equivalence is established. Include evidence type/context in equivalence and keep mixed/conflicting fit visible. Test different nonnumeric warranty/durability assertions, same number with different evidence categories/conditions, unknowns, and two mixed assessments. Do not hide all unfavorable fit merely because it says `conflicts`; distinguish a known mismatch from internally conflicting evidence.

4. **P1 — Display/title edits silently regenerate saved evidence.**
   **Files:** `apps/api/src/shopping/comparisons/service.py:138`; `apps/web/src/features/comparisons/ComparisonPage.tsx:292`; API snapshot contract.
   **Wrong/why:** Every PATCH builds a new view from current evidence/offers and stores a new snapshot. Clicking Show differences only on a stale comparison therefore replaces the displayed historical values, despite the separate Regenerate button and explicit-regeneration contract. Previous snapshots remain in storage, but the active saved view changes without that action.
   **Fix/validate:** Separate presentation edits from explicit data regeneration. Preserve snapshot values, source IDs and capture context when changing title/mode. Define membership/dimension edits explicitly. Test a saved comparison, changed offers/evidence, mode/title edits, then explicit regeneration; only the last step should refresh captured assertions.

5. **P1 — Assistant `add_note` destroys existing note text.**
   **Files:** `apps/api/src/shopping/conversations/proposals.py:125`; `projects/notes.py:106`; `conversations/commands.py:211`; ProposalCard.
   **Wrong/why:** `add_note` calls an upsert which replaces the one note for that target. Two add-note operations for the same target also leave only the final text. There is no note history; project-level existing UserNote text is absent from assistant context. A request to add a concern can erase saved rationale, currently without a visible replacement preview.
   **Fix/validate:** Make addition preserve existing text, or introduce an explicitly previewed replacement operation with the current value/version. Disallow ambiguous duplicate-target operations or define ordered append behavior. Test existing project/product notes, duplicate additions, confirmation/replay, stale proposals, and rollback after a later operation fails.

6. **P2 — Creating/regenerating a comparison makes current fit stale by itself.**
   **Files:** `apps/api/src/shopping/comparisons/service.py:73`, `:195`, `:474`; `evidence/reads.py` assessment freshness; `projects/service.py` revisions.
   **Wrong/why:** Comparison commands advance the project revision before building cells, while assessment staleness compares its project revision to that new revision. Even a just-completed assessment is stale in the new comparison. Re-research followed by regeneration repeats the problem. Notes/decision/presentation edits similarly report changed research context without changed requirements. The plan missed the distinction between transaction revision and assessment-input validity.
   **Fix/validate:** Retain project revision concurrency protection, but determine fit validity from actual saved requirement/context inputs and product/variant revisions (the assessment already stores requirements_snapshot), or another minimal explicit context version. Test research → create/regen, notes/decisions/title changes, and genuine requirement/identity changes. Only relevant input changes should invalidate fit.

7. **P2 — Owner state changes discard saved decision metadata.**
   **Files:** `apps/web/src/features/decisions/ProductDecisionActions.tsx:80`; `apps/api/src/shopping/projects/decisions.py:198`; DecisionEvent model.
   **Wrong/why:** Controls send local `reason` (initially empty), `concerns=[]`, and omit selected_offer_id. The service replaces all these fields. Marking an assistant-shortlisted item purchased clears its rationale, concerns and selected offer; event history does not retain concerns/offer, so those values are lost. Shortlist rationale cannot be entered naturally through these controls either.
   **Fix/validate:** Separate state-only transitions from intentional metadata edits, or initialize/preserve existing metadata and expose rationale/concern/offer edits where required. Explicitly clear only state-specific rejection metadata. Test assistant-created metadata → owner purchased/undo/reject transitions and reload; preserve relevant history and intentional clearing semantics.

8. **P2 — Assistant and manual writes leave active workspace caches inconsistent.**
   **Files:** `apps/web/src/features/assistant/ProjectAssistant.tsx:11`; `projects/ProjectOverview.tsx:141`; `decisions/ProductDecisionActions.tsx:59`; `decisions/UserNoteEditor.tsx:42`; comparison/evidence queries.
   **Wrong/why:** Assistant application invalidates shortlist/rejections/comparison lists but not individual `decision`, `user-note`, or `comparison` queries. Overview's separate assistant callback refreshes only project state. Shortlist can display the applied decision alongside a child control's old state; a note or open comparison stays old. Manual notes/decisions also omit active comparison invalidation; requirement refinements leave cached assessment freshness unchanged.
   **Fix/validate:** Share focused mutation invalidation across both assistant entry points and manual commands, including detail queries and affected evidence context. Preserve dirty drafts. Test confirmed shortlist/reject/note/comparison/refinement on mounted screens, replay, and manual writes; updated state/staleness must appear without reload or window refocus.

9. **P2 — Saved comparisons cannot be edited through the structured workspace.**
   **Files:** `apps/web/src/features/comparisons/ComparisonPage.tsx:108`, `:236`, `:284`; `comparisons/schemas.py` read shape.
   **Wrong/why:** Product/title/dimension builder exists only without comparisonId. Saved views expose mode/regenerate/delete, so users cannot add warranty, remove a deleted requirement dimension, rename, or change membership directly. The effect also hydrates editor state from filtered `dimensions` in differences mode, which omits equal dimensions; returning to the builder can seed an incomplete copy.
   **Fix/validate:** Provide a small saved-comparison editor using the complete persisted definition, separate from filtered presentation. Preserve drafts on failed saves and reset/scoped drafts across routes. Test edits from differences mode, all-equal views, removed requirements, conflicts, and navigation between new/existing comparisons without accidental omitted dimensions.

10. **P2 — Comparison source inspection does not reach the captured evidence.**
    **Files:** `apps/web/src/features/comparisons/ComparisonPage.tsx:314`; `apps/api/src/shopping/comparisons/service.py:305`; existing evidence detail APIs/ProductResearch.
    **Wrong/why:** Evidence cells offer only a live external URL and abbreviated IDs, without the frozen excerpt, qualifiers or evidence category. Fit's Inspect cited evidence link opens the product's default/latest research, not the saved claim IDs/assessment; older or reused evidence may not be present there. Fact cells show no captured origin/excerpt inspection and discard correction_event_id from provenance. The evidence-first UX is weaker than the existing product inspector.
    **Fix/validate:** Route cell source inspection by captured claim/snapshot/offer/observation/correction identity and show qualified evidence type. Reuse the existing evidence service/inspector rather than duplicate rules in comparison code; preserve necessary frozen provenance. Test historical snapshots after newer research/catalog correction, every material cell type, and keyboard focus restoration. Resolve authorized reused-evidence inspection explicitly if evidence detail APIs require a project research attempt.

11. **P2 — Assistant evidence context omits uncertainty and lacks a citation contract.**
    **Files:** `apps/api/src/shopping/conversations/commands.py:246`; `conversations/task.py`; `conversations/schemas.py`; assistant rendering.
    **Wrong/why:** Context includes old assessment conclusions without assessment revisions or context_stale, and claims without computed freshness or contradiction relations. The v2 schema has unrestricted assistant_message but no validated citation fields; validate_output checks mutation IDs, not evidence references. A prompt instruction alone cannot distinguish an outdated assessment or reject a fabricated citation, and chat provides no structured source inspection for answers.
    **Fix/validate:** Supply bounded freshness/context/conflict metadata and an inspectable, owner-scoped citation representation for evidence answers, validated against supplied evidence. Do not promise full semantic truth validation of prose. Test stale requirements, stale sources, conflicting claims, unavailable/foreign citation IDs, and honest unknown answers. Keep live provider compatibility as a separate check.

12. **P2 — Assistant scope silently excludes selectable variants and current selection.**
    **Files:** `apps/api/src/shopping/conversations/commands.py:214` (`limit(8)`); `conversations/task.py:269`; web ProjectAssistant/ComparisonPage; deterministic fake.
    **Wrong/why:** Context always selects the earliest eight project products. A ninth valid variant is unavailable to validated proposals, including edits to a saved comparison containing it. Current screen/comparison and checked products are not supplied, so “compare these” cannot reliably resolve UI selection. Fake commands choose the first products, which does not validate intended targeting.
    **Fix/validate:** Keep bounded context but prioritize explicitly scoped selected/mentioned comparison members, disclose omitted context, and clarify ambiguous targets. Test >8 products, later selected variants, existing comparison edits, and ambiguous “these”; never silently act on the first candidate.

13. **P2 — Note drafts are not scoped when the target changes.**
    **Files:** `apps/web/src/features/decisions/UserNoteEditor.tsx:16`; `products/ProductDetailPage.tsx:174`.
    **Wrong/why:** Changing project/product props changes query and save target but leaves draft/edited state intact. With edited=true, the new target's saved note never hydrates. Product detail does not key this editor by target; cached route transitions can reuse it and send product A's draft to B.
    **Fix/validate:** Scope drafts/mutations to project and exact membership; preserve pending drafts under their original target or explicitly handle navigation, without carrying them into another target. Test rerender/navigation between cached products/projects while dirty and during a pending save; no cross-target write or late-response replacement.

14. **P2 — Project notes now have two unrelated durable stores.**
    **Files:** `apps/web/src/features/projects/ProjectOverview.tsx:463`, `:578`; `projects/models.py` ShoppingProject.notes/UserNote; project/note APIs; assistant context.
    **Wrong/why:** The existing Overview Notes field still edits ShoppingProject.notes, while the new Private project note edits UserNote. They have different content/save paths and neither is included in project-level assistant context. Existing project notes do not populate the new workspace note. The plan did not address the Phase 1 note store, leaving two apparently equivalent features and fragmented decision context.
    **Fix/validate:** Choose/document one authoritative project-note UX, preserve existing content when migrating or reconcile both explicitly; supply relevant project notes to assistant context within bounds. Avoid introducing a larger note system. Test a seeded Phase 5 project with notes, upgrade, UI editing, reload and assistant addition with no lost text.

15. **P2 — New workspace lists silently truncate durable state.**
    **Files:** `apps/web/src/features/decisions/ShortlistPage.tsx`; `features/comparisons/ComparisonPage.tsx`; `features/research/ResearchPage.tsx`; `features/products/SavedProductsPage.tsx`; `api/client.ts:311`.
    **Wrong/why:** These views fetch only the first page and ignore next_cursor (50 decisions/comparisons, 100 variants/favorites). Older rejections cannot be undone from the screen, later variants cannot be compared/researched, and saved counts imply completeness. Decision client helpers do not expose paging.
    **Fix/validate:** Add lightweight cursor pagination/load-more or explicitly communicate and navigate a bounded result set. Test >50 decisions/comparisons and >100 products/favorites, stable ordering, no duplicates, and reaching later items.

16. **P1 — Authored PostgreSQL regression tests contain guaranteed failures.**
    **Files:** `apps/api/tests/projects/test_decision_comparison_api.py:107`, `:144`, `:252`.
    **Wrong/why:** TestClient.delete has no json parameter in the installed transport; both DELETE calls raise TypeError before reaching the API. The differences test lists tank_capacity first (known unequal 12 L/12 gal), then asserts its cells are unknown; it meant warranty. It also codifies silent snapshot regeneration on display-mode change, contrary to the contract. These are test defects, independent of unavailable PostgreSQL.
    **Fix/validate:** Use client.request('DELETE', ..., json=...), assert dimensions by key, and update snapshot expectations with finding 4. Run the actual DB suite after fixing these tests; do not weaken unknown/unit/provenance invariants to get a green result.

17. **P1 — Required MVP gate validation is missing, including unimplemented E2E coverage.**
    **Files/components:** migration `0013_mvp_decisions_comparisons.py`; `apps/api/tests`; `apps/web/package.json`, missing `apps/web/tests/e2e/`; Phase 6 plan/review/VALIDATION.md.
    **Wrong/why:** PostgreSQL integration/model parity, seeded Phase 5 upgrade, concurrent writes, and browser journey/manual review remain unverified. The Playwright suite and test:e2e command were never implemented; package availability is not a disposition of that requirement. Current Phase 6 cases do not cover decision/note/favorite concurrency, cross-owner/tombstone boundaries for all new APIs, or a failing later Phase 6 proposal operation rolling back earlier operations.
    **Fix/validate:** On a usable disposable PostgreSQL 16 host, run pytest -m db, seeded predecessor upgrade, downgrade/re-upgrade and alembic check, with meaningful concurrency/atomicity/ownership/replay tests. Add deterministic vacuum plus chair/monitor browser journeys through requirements → discovery → normalization → research/conflicts → comparison → shortlist/reject/note → restart/reload, including failure/recovery and stale proposal/comparison. Inspect desktop/320px, keyboard and exact citations. Record one live provider/source audit separately when available; do not claim live product quality from fakes. Update gate evidence only after checks run. No distributed infrastructure/Phase 7 scope is needed for these fixes.

Verification performed in this review:

- Existing offline API suite: **133 passed, 97 deselected**.
- Existing frontend suite: **57 passed across 6 files**.
- Ruff check/format, generated API types check, TypeScript, ESLint and Vite build: **passed**, invoking installed binaries directly.
- Small read-only Python harnesses reproduced the dictionary-dimension AttributeError, distinct unnormalized evidence being marked equal, and current fit becoming stale after comparison revision advancement. Inspected the installed TestClient.delete signature to establish the DELETE test defect. These harnesses used mocked sessions and do not establish PostgreSQL transaction behavior.
- `make validate` stopped at the default uv cache sandbox permission; its deterministic constituent checks above ran directly. A fresh disposable initdb attempt with mmap settings failed with `shmget: No space left on device`; **no DB integration tests ran**. No shared-memory resources or user database were modified to work around it.
- Browser E2E, manual browser inspection and credentialed provider audit were not performed. Existing passing mocked tests do not establish those behaviors.

The single-state decision model, project locking/version checks, exact membership validation, offer-variant checks, independent favorites, transactional proposal application, read-only GET behavior, and additive persistence approach are sensible foundations. No new concrete cross-owner disclosure, provider-cost loop, or need for service/infrastructure expansion was found in the inspected Phase 6 paths. Fix the listed behaviors with focused changes and regression coverage; avoid unrelated redesign. Keep the existing gate open until findings are resolved or explicitly disposed and required evidence exists.

## Implementation response — 2026-10-05

The working tree now contains focused fixes for findings 1–16:

1. Proposal confirmation previews shortlist, reject, note, and comparison operations, including exact targets and comparison contents. Unsupported operation shapes disable Apply.
2. Comparison PATCH retains typed dimensions. API regressions cover dimensions-only and combined edits.
3. Difference equality includes normalized assertion text, evidence category, and qualifiers. Mixed assessments remain visible as conflicts; offline equivalence and freshness tests cover these rules.
4. Title and display-mode edits preserve the active data snapshot. The saved editor sends only changed fields; a frontend regression checks title and display-mode request bodies.
5. Assistant notes append in operation order and keep existing text. Project notes consolidate legacy rows; assistant context includes the merged project note.
6. Fit freshness compares the saved requirement inputs and product/variant revisions, not unrelated project revision changes.
7. State-only decision changes preserve rationale, concerns, and selected offer. Transition events retain concerns and offer identity. The workspace lets owners edit rationale, concerns, and offers.
8. Workspace mutations share query invalidation, including decision, note, comparison, and research details. Writes that return the new project revision update the cache without refetching over it; note drafts remain bound to their target.
9. Saved comparisons can edit membership, title, and dimensions from the complete `definition_dimensions` definition, including when the view is filtered to differences.
10. Comparison cells expose captured evidence excerpts, qualifiers, evidence type, observation/correction provenance, saved assessment identity, and inspectable claim citations.
11. Assistant context includes claim freshness, claim relations, and assessment input freshness. Citation IDs are returned, checked against supplied claims and assessment citations, and rendered as inspectable citations.
12. Explicit selected variants and saved-comparison members lead the bounded context; omitted counts are disclosed to the assistant, and the deterministic fake asks for scope instead of choosing the first product.
13. Note drafts reset when the project or exact membership changes; pending mutations update only their original target's cache.
14. `ShoppingProject.notes` remains the project note surfaced in Overview. Legacy project-level `UserNote` text is merged into that field and consolidated on writes.
15. Project products, saved comparisons, shortlist/rejection decisions, favorites, and research views expose cursor-based load-more controls.
16. The DELETE tests use `client.request(..., json=...)`; difference assertions identify dimensions by key, and display-mode changes assert snapshot preservation.

### Validation after implementation

- API offline suite: **138 passed, 100 database/live tests deselected**.
- Frontend suite: **61 passed across 6 files**. TypeScript, ESLint, and Vite production build passed.
- Ruff check/format and generated API type check passed.
- No database test reached PostgreSQL: `TEST_DATABASE_URL` is not configured. The earlier disposable PostgreSQL initialization also failed with `shmget: No space left on device`.
- Browser E2E infrastructure/journeys, desktop and 320px/keyboard inspection, downgrade/re-upgrade and schema parity against PostgreSQL 16, concurrent DB writes, and a credentialed source audit remain unverified. There is no Playwright dependency or `test:e2e` script in this workspace.

**Phase 6 gate remains open under finding 17.** Run the PostgreSQL migration/integration suite on a disposable PostgreSQL 16 database, add and run the browser journey suite, complete the specified manual inspections and live source audit, then record that evidence before closing the gate. Do not treat the passing offline suites as substitutes for those checks.
