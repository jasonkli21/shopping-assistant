# Phase 8 — Personalization and explicit memory boundaries

Status: implemented locally; external verification open; not accepted. Phase 6 and Phase 7 review gates remain open; this code slice proceeded at the user's explicit direction without passing either gate. Read the [index](implementation-plans-index.md), product learning principle, Personal AI integration contract, preferences module notes and ADR 0003.

## Outcome, slice and boundary

A user promotes “prefers compact furniture” from a project suggestion to an editable shopping preference, sees its origin, chooses whether to use it in another project and can revoke it. “Must fit under this 27-inch desk” remains local unless explicitly selected for broader reuse. Cross-application memory receives no writes without an explicit user action and verified API contract.

Smallest slice: project-local judgment → visible preference candidate → accept into shopping profile → next-project suggestion → explicit requirement application. Scope includes profile/preferences, promotion/edit/delete, provenance, conflict rules and optional Personal AI memory adapter. Exclude silent learning, autonomous profile mutations, receipts/email/travel/finance integrations, collaborative profiles, embeddings/vector stores and broad user modeling.

## Contracts and distinctions

`preferences/` owns shopping profile/candidates/preferences/context-selection; `integrations/personal_ai/` owns optional external memory wire mapping. `projects/` remains the authority for project requirements. Conversations/research request a bounded explicitly selected context snapshot rather than reading unrestricted memory. Canonical products/claims/offers remain separate from preferences.

Three scopes must stay visible:

1. **Project-local shopping context:** project budget/requirements, decisions/rejection reasons/notes and project conversations. Existing records remain authoritative for that project and do not become profile data by repetition alone.
2. **Durable cross-project shopping preferences:** shopping-owned profile, typed soft preferences, user-confirmed applicability/categories, origin and revision. They suggest initial requirements; they do not overwrite explicit project constraints.
3. **Cross-application Personal AI memory:** separately owned external platform context. Retrieval is optional and constrained; promotion is a distinct explicit proposal operation with external IDs/status. This repo stores references/consent/sync result, not a duplicate memory database.

Tables:

- `shopping_profiles`: UUID, owner unique, revision/timestamps and minimal settings (e.g. context reuse enabled). No sensitive demographic inference.
- `shopping_preferences`: profile FK, bounded key/value/unit, category applicability, strength `soft` initially (hard constraints require project confirmation), human-readable label, active/revoked status, origin/source project+judgment references, accepted/updated times and revision. Money-specific preferences retain currency and cannot apply universally across categories without explicit choice.
- `preference_candidates`: owner/project, source references and context revision, proposed label/value/applicability, rationale and pending/accepted/dismissed/stale status. Deduplicate by source/normalized proposition; dismiss prevents immediate re-proposal from the same source/version. Candidates never affect research until accepted/applied.
- `memory_operations` only if external integration is verified: owner/preference, request_key/hash, action `propose|retract`, external reference, pending/succeeded/failed/unknown state, consent scope/time, attempt/error metadata. This is a bounded operation audit, not a general sync framework.

API reads/patches profile/preferences with expected_profile_version; promotion accepts candidate ID and explicit scope. Candidate stale project context returns 409 requiring reconfirmation, not silent broadening. Revocation and reuse-off stop new profile suggestions and application. A requirement already copied into a project remains independent local project context, including in later requests for that project, until the user edits or removes it; historical run snapshots remain labeled as historical context, with privacy purge policy from Phase 9. External memory deletion/retraction is separate and must show its real outcome; local deletion cannot falsely claim external memory removal.

Context precedence: explicit current project requirements > user-confirmed project selections > applicable active shopping preferences > optional external suggestions. Contradictions surface as suggestions/clarification, never silently relax hard constraints. Each selected preference's ID/revision/scope is included in the research/AI input snapshot for reproducibility. Revocation affects future calls; it does not rewrite old assessments. Omit unrelated/cross-owner memory and bound count/size (start at at most 20 relevant preference items, configurable downward).

## Work packages

### 8A — Local profile and promotion lifecycle

Migrate profile/preferences/candidates, add owner-scoped services and API/types. First support manual candidate creation/promotion from a selected requirement or rejection judgment; automatic candidate suggestion can then use a shopping AI task, never automatic acceptance. Task `propose_shopping_preference.v1` returns bounded candidate propositions with exact source IDs and explicit local-vs-general rationale; reject foreign/missing IDs or ungrounded sensitive inference. Transactional acceptance writes preference and candidate status once; request replay cannot duplicate it.

Test single-project-specific dimension, category budget versus generic preference, duplicate promotion, dismissed candidate, stale source, edit/revoke and foreign-owner access. Source references can become unavailable after privacy purge; show that rather than retaining deleted private content secretly.

### 8B — Profile UX and bounded reuse

Shopping Profile lists active/revoked preferences with scope, provenance and edit/delete controls. Project Overview can propose selected profile preferences as editable requirements using the established proposal service. Initial project form may show applicable suggestions but does not auto-apply. Assistant shows “using these preferences” and allows disabling reuse for a project. Mobile uses simple labeled forms, not a dense settings table.

Test loading/empty/error/conflict, source inspection, acceptance/dismissal and confirmation, revocation across reloads and explicit project overrides. A profile change cannot mutate an already-edited project invisibly. Favorites/purchased/rejections remain decisions unless explicitly promoted.

### 8C — Optional external memory contract and adapter

Inspect actual Personal AI memory API/capabilities. Define `retrieve_context` and `propose_memory`/retract methods only if they exist or can be faithfully adapted. Document auth, user scope, data shape, consent, idempotency and deletion capability. Never import Personal AI internals or send an entire transcript by default. Payload contains only user-approved compact preference content and origin reference approved for that scope.

If unavailable, ship local reuse with external controls disabled/clearly unavailable; keep an explicit external gap. Do not invent a working memory endpoint. If available, use deterministic adapter fixtures plus opt-in live tests. Persist operation intent before I/O and handle uncertain success after timeout without duplicate external writes; use verified provider idempotency or explicit reconciliation/manual retry. A failed external write does not roll back a separately accepted local preference; show local accepted/external pending status. External retrieval outage leaves local projects fully usable.

### 8D — Evaluation, privacy review and completion

Create `tests/evals/preferences/` for compact-furniture promotion, desk-height locality, category-specific budgets, one-time gift constraints, already-owned rejection, revocation and conflicting imported suggestions. Require zero automatic memory writes/promotions and zero cross-owner context leaks. Review log/snapshot retention and least-data payloads, update API/docs and selected-contract status. Suggested commits: local schema/lifecycle; profile/context UX; conditional memory adapter; eval/privacy evidence.

## Acceptance and verification

Explicit shopping preference reuse works across two projects and remains editable/revocable. Original project state is unchanged by profile changes. Project constraints win conflicts and the UI explains which context is selected. No one-time requirement silently becomes global. Optional external operations require explicit user scope and report actual success/failure/unknown; unavailable memory is a documented limitation, not a blocker to local personalization.

Run `make validate`, PostgreSQL preference/promotion/snapshot tests, prior migrations/metadata, OpenAPI/types check, `uv run pytest tests/evals/preferences` and E2E project→promote→reuse→revoke with fakes. Separately test real memory retrieval/proposal/retraction only against a safe test identity when supported; record exact operation IDs and unverified deletion semantics. Never report those as passed from mocks.

Review: Are all three scopes distinguishable? Does revocation prevent future context use? Can an unrelated project bias research? Are external consent and local preference acceptance separate? Does snapshot history avoid silent retroactive changes while supporting privacy purge? Is the feature usable without external memory?

Handoff: owner-scoped profile/preference schemas, explicit promotion and reuse service, context precedence/snapshot provenance, consent/operation audit if implemented and real Personal AI contract note. Phase 9 must secure every new profile/memory endpoint, minimize logging and implement export/purge. Remaining external gap: Personal AI memory API/auth/idempotency/retraction capabilities; no cross-application integration beyond this verified boundary.

## Local implementation record — 2026-10-05

The local slice supports manual promotion from either a saved project preference or a rejected-product judgment. It deliberately does not run automatic extraction or acceptance. A selected rejection becomes only a pending candidate; profile acceptance and application to another project remain separate user actions. The Phase 6 gate and Phase 7 acceptance remain open.

Implementation commits: `98b415b` (API, persistence and boundary evaluations) and `e08e485` (profile and project UX). This record and the cross-phase handoff are in a separate documentation commit.

| Acceptance area | Implementation evidence | Status |
|---|---|---|
| Owner-scoped profile, candidate and soft-preference lifecycle | Migration `0019_explicit_shopping_preferences`; `preferences/models.py`, `schemas.py`, `service.py`, `router.py`; generated OpenAPI types | Implemented locally; PostgreSQL application not run |
| Bounded and typed monetary preferences | Candidate/edit validators require category scope, supported ISO currency, and decimal-string amounts for structured money values | Implemented locally; schema regressions pass |
| Explicit requirement or rejected-judgment promotion, dedupe, stale source, edit/revoke | Preference API and service; `tests/preferences/test_preferences_api.py`; schema tests | Code and deterministic non-DB tests present; API lifecycle tests require PostgreSQL and remain unrun |
| Category-limited cross-project suggestions, explicit application and source snapshots | Project Overview, Shopping Profile, `ProjectPreferenceSuggestions`, `AssistantPanel`; requirement, chat and research snapshots retain preference ID/revision/scope | Implemented locally; browser journey and PostgreSQL snapshot checks remain unrun |
| Hard project boundaries and local-only one-time context | Conversation/research prompt precedence; `tests/evals/preferences/` scenarios for compact furniture, desk height, budgets, one-time gifts, owned rejections, revocation and conflicts | Offline evaluation cases pass; no live model quality claim |
| External Personal AI memory boundary | `integrations/personal_ai/CONTRACT.md` Phase 8 check and profile status UI | No verified user-scoped memory API exists; no adapter or external writes added |

Verification on this host: the deterministic API suite passed 164 tests; frontend Vitest passed 64 tests, TypeScript and ESLint passed, Ruff check/format passed, generated API types were current, Vite production build passed, and Alembic generated offline SQL through migration 0019. The build reports a warning for the main JavaScript chunk (510.65 kB minified).

PostgreSQL preference lifecycle, migration up/down plus model-drift checks, and browser/manual E2E were not run. `TEST_DATABASE_URL` is unset; local `initdb` could not allocate shared memory (`shmget`, no space left on device). The repository-pinned pnpm wrapper also attempted to fetch pnpm 10.34.6 from the unavailable registry, so installed Node tooling was used directly. These limits leave Phase 8 unaccepted and do not change Phase 6 or Phase 7 status. Hosted CI, live provider/model quality, live retailer coverage, and cloud checks remain unrun.
