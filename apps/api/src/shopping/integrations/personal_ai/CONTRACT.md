# Personal AI contract check for Shopping Assistant

**Checked:** 2026-10-07 against the `personal-ai-system` checkout at `983cbab`, including its current working-tree changes. The upstream checkout has uncommitted shared context-builder work; the observations below distinguish checked-in contracts, local in-progress source, and externally callable API routes.

## Decision

Do not add a network adapter. No externally supported upstream transport currently satisfies Shopping's typed task, project-context, and proposal use cases. A registry declaration is not a transport.

Shopping's `PersonalAIClient` remains the application boundary. Its fake is local-only. `UnavailablePersonalAIClient` returns `provider_unavailable` for every request and performs no network call. Production requires `PERSONAL_AI_MODE=external` so it cannot select the deterministic fake; that mode currently selects the unavailable client and is not evidence of a working integration.

## Upstream application contract

The upstream registry defines Shopping with:

- `application_id="shopping"`;
- `workspace_kind="optional"`;
- `memory_namespace="shopping"`;
- sensitivity defaults `conversation=personal`, `memory=personal`, `domain_context=sensitive`, and `client_context=personal`;
- `shopping.product_context` and `shopping.catalog_search` context-provider registrations;
- `shopping.product_action` tool registration; and
- `shopping` as a comparison domain.

The context-provider registrations have `available=false` with reason `application_integration_not_implemented`. The action registration has `available=false` with reason `shopping_actions_unavailable`. These declarations do not provide Shopping Project context, catalog-search context, or mutation behavior. The comparison-domain registration and the separate domain API do not change that status.

Personal AI's `/v1/domains/shopping/lookup` route is implemented for exact barcode lookup and comparison. Its published `domain-lookup-v1` request accepts an 8–14 digit Shopping barcode and returns a saved comparison. These domain routes require the standalone `personal_ai` application scope and no workspace; a `shopping` application label does not authorize or route access to them. The route does not generate Shopping's structured assistant/research tasks, retrieve Shopping project state, implement the registered context providers, or accept Shopping mutation proposals. It is not a suitable adapter for Shopping's AI integration.

The application manifest treats workspace scope as optional. A Shopping Project is the natural candidate for `workspace_id`, but upstream does not yet require a specific mapping on an external integration contract. Do not choose a project-ID encoding or add transport fields until that contract exists.

Owner identity is authenticated and server-derived in Personal AI's request scope. `application_id` and `workspace_id` are namespace/scope labels; neither grants owner access or substitutes for authorization. Shopping must preserve the same rule and enforce its own owner/project permissions.

The `shopping` memory namespace is registry metadata, not proof of a wired runtime namespace or a memory API. Personal AI's shared memory/context functionality does not currently expose Shopping with supported user-scoped memory read, create, edit, propose, retract, or idempotency operations.

## Context-provider and provenance direction

The checked-out upstream Phase 11 source defines typed `ContextSelection` and `ContextItem` contracts. Selections bound provider/operation, fields, entity references, time window, result count, bytes, timeout, required/optional behavior, and target scope. Returned items carry typed payloads plus owner/application/workspace identity, source identity/version and item ID, entity/source references, authority, timestamps/expiry, sensitivity, field-level sensitivity, and permission dependencies. The coordinator validates registered capabilities, scope, provider identity, provenance, sensitivity ceilings, field projections, and request bounds.

Those provider contracts are currently source-level integration seams, not an externally callable Shopping provider API. The committed Phase 11 implementation requires explicit selections and does not provide real Shopping domain providers or automatic context selection. The current upstream working tree contains uncommitted changes wiring selected source items through a shared `ContextBuilder`; the upstream status docs have not yet recorded that work, and it is not a published transport contract or a Shopping integration.

For any future Shopping → Personal AI context, expose only a bounded typed domain view with version and provenance. Keep Shopping's authoritative project/product/offer/decision/preference records in Shopping. Carry applicable authority, freshness, owner/application/workspace scope, and sensitivity metadata; do not send unrestricted database rows or transcripts by default.

## Proposal and mutation direction

Personal AI's target architecture describes domain context flowing to Personal AI and typed proposals flowing back to the domain. The domain authorizes, validates, confirms as required, persists idempotently, and returns authoritative post-state. Personal AI's versioned typed mutation-capability framework remains future architecture; an existing Travel itinerary-proposal route is Travel-specific and does not implement Shopping actions. Shopping must not accept model output as a direct write.

When a Shopping proposal transport exists, Shopping will validate the proposal against current owner authority, domain schemas, project revisions, and hard constraints, then apply it through existing Shopping commands with required confirmation and idempotency.

## External API check

The current public route inventory includes ordinary conversation messages/SSE, conversation context inspection, research, domain lookup/comparison, profile/account APIs, and domain-specific Travel proposals. It does not define a generic Shopping task-generation route with Shopping's typed input/output and refusal contract, nor an externally callable Shopping context-provider/action contract. Conversation SSE is ordinary chat output and cannot stand in for structured Shopping task generation. Conversation context inspection is not Shopping Project retrieval and does not grant access to memory text/vectors as a Shopping integration.

Earlier Phase 2 (2026-10-03) and Phase 8 memory (2026-10-05) checks documented the same task and memory API gaps against the upstream state at those dates. This check updates the current application-registry/provider status without rewriting those historical checks.

## Local configuration

`PERSONAL_AI_MODE=fake` selects deterministic local generation. `PERSONAL_AI_MODE=external` selects the fail-closed unavailable client until a supported external contract and adapter are implemented. There is no `PERSONAL_AI_URL` setting: Shopping does not call a URL or guess an upstream route.

Shopping must not import Personal AI internal Python types or create a shared package merely to align terminology. Exchange a versioned wire contract through the existing Shopping boundary when a supported transport exists.
