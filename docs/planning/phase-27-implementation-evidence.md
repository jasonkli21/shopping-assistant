# Phase 27 implementation evidence

**Recorded:** 2026-10-11
**Status:** Locally partial; Phase 27 is incomplete and not accepted.

## Compatibility inputs

- Shopping starting revision: `ccf597d` (`main`) before this Phase 27 change set.
- Personal AI starting revision: `c2dfe2d` (`main`) before this Phase 27 change set.
- Cross-repository context contract: `shopping-context-read-v1`.
- Project scope is carried as a Shopping entity reference. `workspace_id` is always null.

The implementation adds a read-only, owner-authorized Shopping projection and Personal AI provider adapters. It does not close the whole phase: routed generation and the Shopping-hosted shared sidecar remain unavailable behind the documented prerequisite and host-contract gaps.

## Implemented boundary

Shopping owns `POST /v1/integrations/personal-ai/context` and the typed request/response mapping. Its `current`, `search`, and `verify` operations read the canonical PostgreSQL domain store. Current context returns only requested project fields and exact selected project-product references; requirements preserve hard (`must_have`, `constraint`) versus soft (`preference`) classification, and decisions preserve saved/rejected state. Search returns only existing selected-product offers and evidence claims, grouped with exact project-product, canonical product, and variant IDs while retaining source references, authority, observation time, freshness, and expiry. It does not crawl merchants or promote catalog data to current offer authority.

The endpoint verifies separate Google service and user ID tokens, checks exact configured service/user identity and the operator-supplied mapping reference, resolves the fixed Firebase owner binding, and then checks project ownership before projection. Reads use a repeatable read-only transaction, bounded statement timeout, response/result/field/entity/byte limits, and private no-store headers. Both repositories default their context gate off.

Personal AI implements `shopping.product_context` and `shopping.catalog_search` through its existing deployment-composed `ContextRuntimeContribution`, provider coordinator, deterministic planner, field policy, shared assembler, and permission revalidation contracts. Selected project/product references remain Shopping-domain IDs; no workspace mapping is inferred. Shopping retains canonical state and the existing `PersonalAIClient.generate(AIRequest) -> AIResponse` boundary. `shopping.product_action` remains unavailable.

## Work-package disposition and remaining gaps

- **P27.0 read providers and contract:** implemented locally behind independent default-off gates. The contract is versioned and bounded; generation transport is not part of this read route.
- **P27.0 `PersonalAIClient` task transport:** not implemented. Shopping's worker jobs lack delegated-user identity, and Personal AI has no accepted generic typed-task route. `PERSONAL_AI_MODE=external` continues to select the fail-closed unavailable client.
- **P27.1 research and routed task baseline:** incomplete. No Shopping extraction/rewrite/synthesis work is routed through P21/P24; the open Phase 15 membership/revocation gate still blocks request-workflow integration. Deterministic Shopping workflows and validators remain Shopping-owned.
- **P27.2 sidecar:** incomplete. Shopping has no accepted shared-sidecar host/embed contract. No selected-context disclosure, Copy, or draft insertion is claimed.
- **Mutation:** no shortlist/requirement write path was added. `shopping.product_action` remains unavailable pending Phase 31.
- **README:** no README-visible behavior changed because both new read gates default off and generation/UI behavior is unchanged.

The implementation reuses one Shopping-owned projection for selected products and does not introduce a parallel project store, provider route, worker state, generation client, or mutation mechanism. The post-implementation review follow-up below promotes the owner-scoped projection to an explicit public domain context seam and routes the legacy conversation helper and Personal AI adapter through it.

## Verification

Tested on 2026-10-11 against the starting revisions above plus this working-tree change set.

- `UV_NO_SYNC=1 PATH=<bundled-node-and-pnpm> make validate` — passed. API Ruff check and format check passed; offline API suite **195 passed, 130 deselected**; API types were current; web lint passed; web tests **68 passed**; TypeScript typecheck passed; production web build passed. Vite reported the existing large-chunk advisory; pytest emitted one Starlette deprecation warning.
- Focused context/auth/config suite — **31 passed, 1 database test deselected**.
- `TEST_DATABASE_URL` was absent. The Shopping PostgreSQL integration test, including selected project state, hard/soft requirements, rejected state, evidence freshness, no-write behavior, and foreign-owner denial, was not run against a disposable database.
- Real Google token/certificate verification, deployed identity mapping, cloud/IAM, deployed Shopping revisions, and provider behavior were not exercised.

## Architecture audit

- Shopping remains canonical for project, requirements, products/variants, decisions, offers, and evidence.
- Owner identity is derived server-side; app/workspace labels do not grant access. Service and user credentials are separate, and no credential is persisted or logged.
- Reads remain selected, bounded, read-only, time-limited, and revalidated by project revision before later disclosure. There is no retry or write/idempotency path to reconcile.
- Domain-current project state and external observations remain separate source classes with exact product identity and provenance.
- Personal AI consumes the shared runtime, policy, context assembly, and revalidation seams. Shopping-specific mapping stays in the domain adapter and registry manifest; no provider-name branch was added to generic orchestration.
- No project/workspace mapping, generic Shopping memory API, task-generation transport, product mutation path, or sidecar host was invented.
- Existing barcode lookup/comparison and deterministic/fail-closed generation behavior remain separate and unchanged.

## Independent review focus

Review the Google subject-to-fixed-Firebase-owner attestation and revocation lifecycle; transaction isolation and timeout behavior; whether every project-child mutation advances the revision used for permission revalidation; the selected-only projection and its internal conversation-module dependency; freshness calculations and observation fingerprints; and confirmation that the default-off gates cannot be bypassed through registry metadata. Review task generation and sidecar integration as open Phase 27 work, not delivered behavior.


## Post-implementation review follow-up — 2026-10-11

The owner-scoped current-state projection is now a public domain context seam used by both the conversation compatibility helper and the Personal AI adapter. Product and variant revisions and exact project-product membership are included in source versions and permission dependencies. Catalog evidence is represented one observation per record, each with its exact expiry; recent-first bounded selection carries omitted count and selection-policy version. The adapter retains Shopping entity references and rejects selected products without authoritative membership IDs. Google certificate requests have a three-second maximum timeout and close their session.

The required identity-mapping reference remains a configuration string, not a versioned or revocable authority record. The review finding remains unresolved; both integration gates stay off. Common workflow-routing prerequisites and the accepted shared-sidecar host/identity contract also remain open.

Verification on 2026-10-11: the offline API suite passed (**196 passed, 130 database tests deselected**) and Ruff passed for the changed files. PostgreSQL, live Google identity/certificate verification, cloud/IAM, provider, browser, and sidecar behavior were not exercised.
