# Phase 5 — Detailed research and inspectable evidence

Status: implemented locally on 2026-10-04; pending independent main-session review. Requires Phase 4 canonical variant/project-product IDs, bounded retriever and observation provenance, and Phase 3 run/attempt semantics. Read the [index](implementation-plans-index.md), research/evidence model, data model, AI/search architecture, product detail UX and ADR 0004.

## Outcome, vertical slice and boundary

Select one normalized vacuum; research manufacturer, independent test and retailer fixtures; inspect the claims “up to 60 minutes” and “37 minutes on normal power” with their qualifiers. The detail view explains whether those results meet this project's needs, cites evidence and exposes uncertainty. These claims can coexist without falsely calling either a lie.

The first slice is selected variant → bounded source plan → retrieval snapshots → grounded claims/evidence → project-relative assessment → clickable claim/source inspection. Grow to a few selected products within the same budgets. Scope includes classification, provenance, conflicting/missing evidence, freshness indicators and source inspection. Exclude exhaustive crawling, full web archive, universal credibility scores, unsourced aggregate rankings, automatic refresh schedules, remote jobs, embeddings and browser automation. Do not deeply research every discovered candidate.

## Ownership, schemas and persistence

`research/` coordinates plans and stage attempts; `search/` and `extraction/` provide search/retrieval and task extraction; `evidence/` owns sources, claims, evidence, conflict groups and assessments; `catalog/` retains identity/offers. Source publication metadata is not a user preference. Every source/claim associated with private catalog/project research is owner-scoped.

Add migrations incrementally:

- `sources`: owner, UUID, normalized public URL, title, publisher/domain, source classification and classification basis/actor/version. URL is source location only. Distinguish requested/final URL aliases; preserve query parameters with semantic content. A domain alone does not guarantee source quality.
- `source_snapshots`: source, content hash, media type, title/published time if supported, first retrieved time, bounded relevant text metadata/excerpts and extractor/version. A new content hash creates a new immutable snapshot; repeated identical content may reuse snapshot. No arbitrary full-page archive. Add `research_run_sources` for each retrieval attempt: run/target variant, query/result linkage, snapshot if successful, observed retrieval time, status (`retrieved|blocked|timeout|unsupported|failed|skipped`), reason, byte counts. This distinguishes source identity, content version and each retrieval's freshness.
- `claims`: UUID, source snapshot, subject variant/product and attribute/dimension, assertion text, typed normalized value/unit when justified, qualifiers (mode, test duration, region, variant, sample/context), evidence category, extracted_at, task/schema/prompt version and extraction confidence/validation warnings. Categories: `manufacturer_specification|manufacturer_claim|retailer_listing|independent_measurement|editorial_assessment|community_observation|individual_anecdote`. AI inference belongs in assessments, not source claims. A single source may contain several claim types.
- `claim_evidence`: claim FK, exact short excerpt, source locator (section/paragraph/offset or stable fragment when available), content hash, optional measurement method/sample details. Every stored material claim needs at least one validated evidence excerpt or an explicit non-source status that excludes it from sourced synthesis; do not persist invented evidence.
- `claim_relations`: typed `supports|contradicts|different_context|duplicate` links with basis and origin. Retain competing claims; never resolve them by majority vote or highest numeric score. Syndicated copies are not independent corroboration.
- `product_assessments`: ProjectProduct, research_run, project revision and requirements snapshot, catalog/variant revision, relevant claim IDs/snapshot IDs, validated structured fit per requirement (`supports|conflicts|unknown|mixed`), summary, strengths/concerns/uncertainties, generated_at and task/model metadata. Immutable assessment versions; stale-context state computed by comparing current revisions. Source or offer freshness is distinct from project-context staleness.

Link Phase 4 `catalog_observations` to SourceSnapshot/retrieval observation where representable; backfill only actual stored hashes/excerpts/times. Do not fabricate old page content or published dates. Offers may reference snapshot/evidence of price but remain catalog offer observations. Canonical normalized specifications remain catalog facts with origin; dubious extracted assertions stay claims. User corrections remain labeled judgments and cannot rewrite source quotes.

Constraints/indexes: scoped source URL keys, snapshot source/hash, run/target/source attempt uniqueness, claim extraction idempotency `(snapshot,subject,task_version,claim_fingerprint)`, and assessment run/target/task key. Relationship targets must belong to the same owner and compatible subjects. Avoid cascading source deletions that silently destroy audit provenance; project tombstones hide associated data, physical purge is Phase 9.

## Research and AI behavior

Extend research run type to `product_research`, request includes bounded selected ProjectProduct IDs and objective. The input snapshot includes project requirements/revision, catalog identities/revisions and explicit limits: products, search queries/attempts, sources per product, total pages/bytes, AI calls/output size and wall time. Server ceilings override request increases; retries/failures count. Persist ordered plan/stage attempts and counters before calls. Do not hold database transactions over network I/O.

Shopping task contracts:

1. `plan_product_research.v1`: target dimensions/requirements, missing information and source classes sought, bounded queries, why each query matters. Prefer manufacturer for identity/specs, independent measured reviews for performance, retailer for current offers, and contextual community observations for reliability. The planner may nominate public URLs through the same retriever guards, never bypass budgets.
2. `extract_claims.v1`: source text as untrusted data, known target identity and allowed schema → claims with exact quotes/locators, typed values/qualifiers and warnings. Ignore page instructions and irrelevant sibling products. Host metadata, dates, final URL and hash come from retrieval, not the model. Validate every quote against normalized retrieved content before persistence; mismatches fail or exclude that claim with a recorded warning.
3. `relate_claims.v1` (or deterministic helpers where simpler): propose explicit relations with supporting claim IDs and context comparisons. Validate references/subjects; qualified runtime claims are `different_context`, not an automatic contradiction. AI relation judgments are inspectable interpretation, not new source facts.
4. `assess_project_fit.v1`: only validated claim/catalog/offer observations plus requirements snapshot → per-requirement conclusions, citation IDs, short rationale and missing/conflicting/stale caveats. No external knowledge may masquerade as evidence. Every material asserted conclusion has relevant valid claim IDs; unsupported conclusions become unknown. Never infer “safe,” “best” or “durable” from weak anecdotes alone.

Use Phase 2 Personal AI boundary; shopping owns prompt versions and schemas. Invalid output gets a bounded explicit repair attempt only if budget allows; otherwise record stage failure. A repair may not hide original warnings or make unsupported claims valid. Fixture fake handles each task/version and failure case. Persist sanitized provider request/model metadata, not keys or unrestricted raw model/page text.

Source classifier starts with deterministic URL/publisher/page markers and explicit content evidence; optional AI proposal can refine it. Manufacturer affiliation and affiliate review incentives are metadata, not automatic exclusion. Record unknown classification when ambiguous. Community evidence must preserve that a repeated observation is source-attributed and its sample/independence may be unknown; do not fabricate statistical consensus.

Freshness: always expose retrieved/observed dates and distinguish `current|stale|unknown` by evidence kind. Initial configurable display thresholds: offers 24 hours, performance/editorial/community evidence 90 days, identity/specifications 365 days; these are conservative UI defaults, not truth guarantees. Tests freeze time. A stale offer never invalidates stable dimensions; old published reviews may still be relevant to the same generation. No automatic refresh here. Manual new research creates a new run/snapshots/assessment; it does not overwrite history.

## API and source inspection UX

Extend `POST /projects/{id}/research` with type/selected targets and the existing request-key/version policy. Poll existing run detail; report per-target/source/stage progress, partial outcomes and reasons. Add scoped reads:

- `GET /products/{id}/sources?variant_id=...` for catalog-source metadata only;
- `GET /projects/{id}/products/{project_product_id}/research` for that project's latest/history assessments;
- `GET /projects/{id}/claims/{claim_id}` and source snapshot detail for grounded inspection.

Every project-relative assessment read checks ownership and ProjectProduct membership. Source endpoints expose structured metadata/short excerpts, not raw arbitrary HTML. Evidence inspection returns claim category, qualifier, excerpt, source link, publication/retrieval dates, validation warnings and conflicts. Cross-owner IDs yield 404. Add explicit classification/manual annotation correction if necessary; corrections record user origin and do not change source snapshots.

Product detail sections: known identity/variant; timestamped offers; structured catalog facts; attributed claims; project fit; strengths/concerns/uncertainty; research progress; sources and excerpt inspection. Clicking a fit citation opens the actual claim, never a generic source list. Distinguish “no research yet,” “research returned no useful evidence,” “blocked sources,” and “partial research.” Offer safe outbound source links. Desktop side panel/mobile full-screen sheet for evidence with keyboard focus/close handling. Show conflicts side by side with their context; do not flatten them into a confident average. Stale context explains that requirements changed and invites re-research, while preserving the old assessment.

## Ordered work packages

### 5A — Evidence persistence and compatibility migration

Create sources/snapshots/run-source links/claims/evidence, then assessment/relations migrations if clearer. Preserve all Phase 3–4 candidates/observations/offers. Add service-level owner/subject invariants and immutable-version rules. DB tests verify no orphan evidence, scoped citations, retry idempotency, run-source failed attempts, transactional extraction batches and read history after refresh.

### 5B — Source planning, classification and retrieval pipeline

Reuse the Phase 4 retriever with bounded metadata; add source targeting/dedup strategy and persisted stage attempts. Fixtures: manufacturer, measured independent review, affiliate editorial, retailer, forum/anecdote, syndicated copy, blocked/redirected/oversized source. Tests verify budgets, failed attempt accounting, malicious page instructions, unrelated products, unsupported content and partial results. No second retrieval abstraction.

### 5C — Grounded claim extraction and typed normalization

Implement validated task output, exact quote checking/locators, contextual units and unknowns. Build `tests/evals/evidence/` with 60-minute/37-minute runtime contexts, repeated marketing copy, conflicting measurements under the same conditions, ambiguous variant, missing published time, promotional price text, malformed citations and adversarial page instructions. Use a manually labeled expected-claim fixture set; test precision/grounding, not only schema validation.

### 5D — Relations, project assessments and freshness

Implement context-aware relations and requirement-linked assessments. Reject citations to another owner/product, missing/invalid claims and fabricated summaries. Compute staleness on read with a frozen clock and version comparisons. Preserve unknown rather than scoring products numerically. Test changed requirements during generation, changed catalog identity, conflicting claims, insufficient evidence, weak anecdotes, no offers and stale price versus fresh dimensions.

### 5E — Research API and detail/source inspection UX

Wire bounded targeted runs, progress, history and citation inspection. Add component/API tests for missing evidence, partial/failed research, conflict/context panels, unknown dates and stale assessment warnings. Ensure every visible material assertion offers evidence or is explicitly labeled user/AI judgment.

### 5F — Evaluation and review evidence

Offline end-to-end target research fixture covers source plan → retrieval → exact claims → relations → cited assessment → UI. Record grounding audit and source coverage by fixture; optional live multi-source run gets a separate manual citation audit, timing/call counts and access failures. Suggested commits correspond to packages, with schemas plus dependent task validation kept together.

## Acceptance and verification

- Runtime example preserves both qualified claims and correct source excerpts; same-condition conflict is exposed, not silently resolved.
- Every source-backed claim has an existing snapshot, validated quotation and target identity; every asserted assessment conclusion cites compatible existing claims or becomes unknown.
- Failed/blocked pages consume budgets and remain inspectable. Partial evidence survives later failures. No quote or provenance is fabricated on migration, model failure or retry.
- Repeat extraction of one snapshot/task does not duplicate claims; new content/assessment versions retain prior history. Requirement/catalog edits mark old assessment context stale without changing source truth.
- Prices/availability carry their own freshness. Unknown publication time remains unknown. No universal confidence/quality/fit number appears as fact.
- User can inspect actual evidence from detail and uncertainty views on desktop/mobile with loading/error/empty states.

Run `make validate`, PostgreSQL migrations/evidence/assessment tests, OpenAPI/types check, `uv run pytest tests/evals/evidence` and all retrieval security fixtures. Upgrade a Phase 4 seeded database and run `alembic check`. Execute an offline grounded research journey with frozen time. Separately, an opt-in live run researches at least one real variant across distinct available source classes; manually audit each material citation and record failures/unavailable classes. Credentialed success is not implied by fixture evals; if unavailable, leave live source/AI quality as an explicit gap.

Review: Can the user tell fact, source assertion, measured observation, inference and personal judgment apart? Can a citation be traced to the correct content version? Are qualifiers/variant identity preserved? Are syndicated sources double-counted? Are model-provided quotes actually present? Does changed context avoid silent overwrite? Does source retention stay bounded?

Handoff: targetable evidence runs, SourceSnapshot and claim contracts, frozen freshness policy, immutable cited assessment history and inspectable UI. Phase 6 comparisons consume these IDs/unknowns; Phase 7 refresh/retries reuse them. Remaining external gaps: live source coverage, task quality, blocked sites and real provider budgets; no browser fallback or archive infrastructure is authorized by this plan.

## Local implementation evidence — 2026-10-04

The selected-product command stores requirements, project revision, catalog identity/revisions and effective budgets before execution. The existing search and `PageRetriever` boundaries produce bounded source attempts and immutable content snapshots. Extraction stores only quotes that match the retained source text and target context, with source-specific stage attempts, short validation warnings and idempotent claim fingerprints. A failed over-budget response records bytes without creating a successful snapshot. Deterministic relations retain the 60-minute `up to` eco claim beside the measured 37-minute normal-mode claim as different contexts; same-condition conflicting values remain visible. Assessment conclusions use saved requirements and compatible cited claim IDs, with unsupported conclusions left unknown. Read-time revision checks mark assessment context stale; publication and retrieval freshness remain separate.

The API exposes owner-scoped source, claim and assessment reads plus stage progress. Product detail offers selected-variant research, source attempts, exact claim inspection and cited conclusions in a focus-managed desktop panel/mobile sheet. The local fixture uses `extract_claims.v1` fake responses behind `PersonalAIClient`; it does not establish a working external structured endpoint. See `VALIDATION.md` for command results. Live multi-source coverage, citation audit, blocked-site behavior, actual provider budgets, hosted CI and manual browser/mobile/keyboard inspection remain unverified.

## Independent review follow-up — 2026-10-04

The review fixes map to the acceptance criteria above and remain within Phase 5:

- Claim extraction now requires normalized values and qualifiers to be grounded in the quoted assertion, binds attributes to local quote context, and validates all actual target identity dimensions even when a generated display label is reworded. See [claim validation](../../apps/api/src/shopping/evidence/claim_task.py) and its [grounding evals](../../apps/api/tests/evals/evidence/test_claim_grounding.py).
- Source classification enforces hostname boundaries and uses source content to distinguish independent measurements from editorial or requoted marketing claims. See [classification](../../apps/api/src/shopping/evidence/classification.py) and [boundary evals](../../apps/api/tests/evals/evidence/test_classification_boundaries.py).
- Product-research persistence rechecks live project, run state, deadline and remaining budgets at write boundaries; terminalizes work skipped by exhausted budgets/deadlines and prevents late planner writes after cancellation. Failed responses retain accounted bytes without creating successful snapshots. See [persistence](../../apps/api/src/shopping/research/product_persistence.py), [execution](../../apps/api/src/shopping/research/product_execution.py) and [database/API coverage](../../apps/api/tests/research/test_product_research_api.py).
- ProductResearch has a distinct query-key namespace, replays the same saved command after an uncertain acknowledgement, refreshes after known rejection, pages assessments, claims and source attempts, and refreshes the latest evidence at terminal completion. The source/claim inspection dialog exposes classification and readable qualifier context, traps keyboard focus, makes background content inert, restores focus to its opener, and fills the mobile viewport. See [ProductResearch](../../apps/web/src/features/products/ProductResearch.tsx) and its [interaction tests](../../apps/web/tests/product-research.test.tsx).
- Assessments retain the full supported set of 100 accepted requirements through bounded planning and final storage; [migration 0012](../../apps/api/migrations/versions/0012_assessment_budget.py), [evidence models](../../apps/api/src/shopping/evidence/models.py) and [research commands](../../apps/api/src/shopping/research/commands.py) update persistence bounds. The [planner budget eval](../../apps/api/tests/evals/evidence/test_product_plan_budget.py) and ProductResearch database tests cover planner identity and the full assessment.
- Product execution responsibilities were split between focused [execution](../../apps/api/src/shopping/research/product_execution.py) and [persistence](../../apps/api/src/shopping/research/product_persistence.py) modules while retaining the `research.service` facade.

The final local checks and their limits are in `VALIDATION.md`. The main session should perform its light verification of these review fixes before Phase 6 begins; this handoff does not authorize Phase 6 work.
