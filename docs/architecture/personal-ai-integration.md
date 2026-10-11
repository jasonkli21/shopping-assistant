# Personal AI Integration

## Current status

Shopping is registered in `personal-ai-system` as `application_id = "shopping"`. Personal AI now has gated, typed providers for Shopping's read-only `shopping-context-read-v1` contract. Shopping serves that contract at `POST /v1/integrations/personal-ai/context`, with separate service/user Google identity verification and Shopping-owned owner/project authorization. Both repositories default this context integration off.

Shopping's `PersonalAIClient.generate(AIRequest) -> AIResponse` is its local boundary for AI-dependent work. The deterministic fake supports local development and tests. The external implementation is deliberately unavailable and returns `provider_unavailable`; no network request is made. Production requires `PERSONAL_AI_MODE=external` to prevent fake generation, but that setting does not prove or enable a working upstream integration.

## Application scope and registry

The upstream application definition currently declares:

- `application_id = "shopping"`;
- optional workspace scope;
- `memory_namespace = "shopping"`;
- sensitivity defaults of `personal` for conversation, memory, and client context, and `sensitive` for domain context;
- `shopping.product_context` and `shopping.catalog_search` context-provider capabilities;
- `shopping.product_action` as a tool capability; and
- the `shopping` comparison domain.

The two context capabilities have implementations and are guarded by `SHOPPING_CONTEXT_ENABLED`; the Shopping read API has its own `PERSONAL_AI_CONTEXT_ENABLED` gate. `shopping.product_action` remains unavailable for writes. The `shopping` memory namespace is still metadata and does not provide a Shopping memory API.

Personal AI's `/v1/domains/shopping/lookup` route is a separate implemented API for exact barcode lookup and comparison. It does not expose Shopping Project state, implement the registered Shopping context providers, generate Shopping's typed assistant/research tasks, or accept Shopping mutation proposals. It is not a transport for this integration.

`application_id` and optional `workspace_id` describe request scope; neither authorizes access. The owner must be authenticated and derived by the server. A future integration must continue to enforce owner and workspace access independently of the supplied application/workspace identifiers.

A Shopping Project remains a domain entity reference, not a Personal AI workspace. The v1 request explicitly sets `workspace_id` to null and carries `project_id` separately.

## Domain authority and shared runtime

Shopping remains authoritative for Shopping Projects, requirements, products and variants, offers, decisions, preferences, and Shopping evidence. These records stay in Shopping's PostgreSQL domain store.

The read projection returns only requested fields and selected project-product references. Project data is marked authoritative and sensitive; stored offer/research claims are separate external observations with provenance and freshness. The endpoint uses a read-only repeatable transaction, bounds result count/bytes/time, and has no mutation operation.

`personal-ai-system` is the shared AI platform. The Shopping provider contribution uses its deployment-owned context runtime, planner, provider coordinator, application field policy, assembler, and permission revalidation. This does not move domain state or validation into Personal AI. The Shopping app's queued generation workflow remains separate: it still has no supported typed task transport or delegated user identity. The frontend also has no accepted shared-sidecar embedding contract. Phase 27 is therefore incomplete; the read integration does not establish routed generation, sidecar behavior, or live deployment readiness.

## Future data exchange

The `shopping-context-read-v1` contract now carries selected Shopping context to Personal AI with owner/application scope, exact project/product/variant identity, source version/references, authority, freshness/expiry, sensitivity, and permission dependencies. Catalog observations are grouped under their selected Shopping product identities. Reads remain bounded by selected product IDs, fields, result count, bytes, and time; workspace scope is null.

Task generation remains future integration work. A supported task API must preserve the existing Shopping-owned `PersonalAIClient` request/response contract and provide an authorized delegated-user identity through the queued worker lifecycle before Shopping can select it as an external implementation.

Personal AI → Shopping changes should arrive as typed, versioned proposals or capability results only after the Phase 31 mutation framework and Shopping validation/confirmation contract exist. Shopping must perform owner/domain authorization, validate project revisions and hard constraints, enforce idempotency and any required user confirmation, persist the authoritative change, and return the resulting Shopping state. Personal AI must not write Shopping records directly.

Do not import Personal AI internal Python types into Shopping or create a shared package merely to align names. Agree on an external, versioned wire contract when an actual transport is available; map it inside Shopping's `PersonalAIClient` boundary.

## Related contracts

See the [Shopping integration contract check](../../apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), [ADR 0003](../adr/0003-personal-ai-boundary.md), and `personal-ai-system/docs/personal-ai-chapter-2/02-target-architecture.md` in the sibling checkout for upstream details.
