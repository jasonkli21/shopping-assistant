# Phase 6 repository review

Review date: 2026-10-05  
Status: **gate open; Phase 7 was later explicitly authorized and implemented locally without passing this gate**

This report records the main-session review of the Phase 6 implementation. Product, API, architecture, data-model and ADR guidance were compared with the code and focused regression coverage. The decision, comparison and workspace implementation is present locally, but acceptance evidence is incomplete. In particular, this report does not claim that the end-to-end MVP gate passed.

The original sequencing recommendation below was superseded by an explicit user request to implement Phases 7 and 8 while this gate remained open. That authorization did not pass or waive the Phase 6 gate. See [`../current-state.md`](../current-state.md) for the live boundary.

## Reviewed boundaries and behavior

| Area | Evidence reviewed | Finding |
|---|---|---|
| Module direction | `api/router.py`; project, catalog, comparison and conversation modules | API aggregates routers. Decisions/notes live in `projects/`, favorites in `catalog/`, saved comparisons in `comparisons/`, and validated assistant operations in `conversations/`. Comparison construction reads stored catalog/evidence rows and does not call search, page or AI providers. No new infrastructure or service split was introduced. |
| Exact product identity | `ProjectProduct` joins in decisions, comparison and assistant current-state reads | State and comparison membership use exact ProjectProduct/variant identity. Selected offers must match that variant. Assistant IDs are checked against a bounded, owner-scoped current-state snapshot before a proposal is persisted and again when it is applied. |
| Ownership and private data | `decisions.py`, `notes.py`, `favorites.py`, `comparisons/service.py`, `conversations/commands.py` | HTTP reads and mutations scope project, variant, note, offer and evidence rows to the current local owner. The Phase 9 authentication boundary remains unchanged; these local-owner APIs are not a public deployment claim. |
| Revisions and transaction scope | Project row-locking services; `proposals.py`; comparison/decision API tests | Project-context mutations validate project revisions and increment once. Decision command replay is keyed and payload-checked. Favorites use an independent version. Assistant decision/note/comparison work is applied in the proposal transaction after explicit confirmation. Database concurrency behavior still needs PostgreSQL execution evidence. |
| Provenance and uncertainty | `comparisons/service.py`, `ComparisonSnapshot`, Phase 5 evidence models | Snapshots retain exact product/variant revisions, offer/observation IDs, claim/snapshot IDs, assessment/claim references, fact origin/observation metadata and note versions. Unknown, conflicting, stale and incomparable values stay visible. Offers preserve currency and observation time; GET computes staleness without regenerating snapshots. |
| Comparison equality | `_normalize`, `_demonstrably_equal`, `tests/comparisons/test_comparison_equivalence.py` | Equivalent supported units normalize deterministically. The review caught and fixed equality that omitted the unit for unsupported conversions; equal numeric values such as 12 L and 12 gal now remain distinct in differences mode. Decimal normalization removes formatting-only scale differences. |
| Migration and deletion | `0013_mvp_decisions_comparisons.py`; metadata imports in `migrations/env.py` | The additive migration creates decisions/events, notes, saved products, comparison membership/dimensions and immutable snapshots with bounds, uniqueness, checks and delete behavior. Offline SQL generation succeeds. Online upgrade, downgrade/re-upgrade, seeded predecessor-data compatibility and `alembic check` could not be run because PostgreSQL cluster initialization fails on the host shared-memory limit. |
| Assistant and SSE | v2 task/schema, command current-state snapshot, proposal application and existing conversation stream | New actions are strict typed proposal operations; prose does not mutate state. Existing stream status/proposal events remain the transport, and durable writes stay behind the confirmed proposal endpoint. Database proposal transaction and stale-preview regressions are authored, but cannot be executed here. External Personal AI compatibility remains unverified. |
| Retrieval, budgets and logging | Comparison service and existing research/retrieval boundaries | Comparison adds no outbound retrieval. Existing research budgets and `PageRetriever` boundary remain in place. New feature services add no provider-error logging path. No live provider audit or production privacy-log inspection was possible. |
| UI and accessibility | Workspace components, route/nav changes, responsive CSS and Vitest tests | Desktop/mobile routes, decision controls, notes, favorites, differences table, empty/loading/conflict handling and save-draft behavior are implemented. The comparison table has a scrollable narrow layout. Automated unit/interaction coverage passes; keyboard-only traversal, 320px visual inspection, focus/evidence-panel review and slow/failing backend browser review remain unverified. |
| Performance and budgets | Input/context caps, maximum 6 comparison products, 20 dimensions and 1 MB snapshot constraint | Data and request sizes are bounded. No latency or query-count measurements were produced; Phase 7 must use fixture measurements before proposing deeper orchestration or caching. |

## Findings and disposition

| Severity | Finding | Disposition |
|---|---|---|
| P1 — acceptance blocker | PostgreSQL migration, model parity, concurrency and API integration tests were not executed. Both the restricted and escalated disposable-cluster attempts failed during `initdb` with `shmget: No space left on device`. | Unresolved environment blocker. Rerun `pytest -m db`, migrate a disposable database, and `alembic check` on a usable PostgreSQL 16 host before passing the gate. |
| P1 — acceptance blocker | The planned Playwright journey suite has not been added or run. This checkout has no Playwright dependency/browser executable, and no live API journey or browser visual/manual inspection was possible. | Unresolved scope/verification gap. Add `pnpm test:e2e` with deterministic providers and disposable PostgreSQL, then review the journey at desktop and 320px with keyboard/citation inspection. |
| P2 — external verification | Live Personal AI structured output and live retailer/source coverage have not been audited. | Keep credentialed checks separate; run and record an end-to-end source audit when credentials and provider access are available. Deterministic fakes do not count as live quality evidence. |
| P2 — operational verification | Hosted CI and multi-instance behavior remain unverified; no Git remote or deployment was used. | Existing phase policy assigns hosting and distributed lifecycle work to Phase 9, after the Phase 6 gate and successor decisions. |

No code-level authorization, revision, provenance or unsupported-unit equality blocker was found in the reviewed paths after the local correction and regression tests. That conclusion is limited to code inspection and tests that could run; it does not clear the unresolved P1 acceptance blockers above.

## Gate decision

**Do not pass the Phase 6 gate yet.** Required PostgreSQL behavior and the planned browser journey remain without evidence. The original instruction not to begin Phase 7 is superseded as stated above; Phase 7 implementation does not close this gate. Update this report and the [validation record](../../VALIDATION.md) only after those checks have actually run.

## SA-05 evidence update — 2026-10-07

The historical findings above record the state at the 2026-10-05 review. The [SA-05 validation entry](../../VALIDATION.md#sa-05-deterministic-browser-acceptance--2026-10-07) now records the deterministic Playwright journey, local PostgreSQL integration/migration checks, and model-drift check. This updates only the missing browser/online-PostgreSQL evidence. Phase 6 remains unaccepted while manual browser/source review and the remaining review-finding dispositions are open; hosted CI and live provider compatibility are also unverified.
