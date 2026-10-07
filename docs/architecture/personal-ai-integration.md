# Personal AI Integration

## Current status

Shopping is registered in `personal-ai-system` as `application_id = "shopping"`. That registry entry is an application contract, not a usable Shopping AI connection. The current upstream API does not expose the typed Shopping task, Shopping context-provider, or Shopping mutation contract this application needs.

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

The three Shopping context/action capabilities are registered with `available = false`. Registration records intended capability identity and metadata; it does not implement a provider, tool, transport, or permission. The memory namespace likewise does not provide Shopping with a memory API or prove that Shopping memory reads or writes are available.

Personal AI's `/v1/domains/shopping/lookup` route is a separate implemented API for exact barcode lookup and comparison. It does not expose Shopping Project state, implement the registered Shopping context providers, generate Shopping's typed assistant/research tasks, or accept Shopping mutation proposals. It is not a transport for this integration.

`application_id` and optional `workspace_id` describe request scope; neither authorizes access. The owner must be authenticated and derived by the server. A future integration must continue to enforce owner and workspace access independently of the supplied application/workspace identifiers.

A Shopping Project is the natural candidate for Personal AI's optional workspace scope. The upstream contract does not currently require a particular transport mapping, so do not assume or encode a project-ID-to-`workspace_id` wire mapping yet.

## Domain authority and shared runtime

Shopping remains authoritative for Shopping Projects, requirements, products and variants, offers, decisions, preferences, and Shopping evidence. These records stay in Shopping's PostgreSQL domain store.

`personal-ai-system` is the shared AI platform. Its current and planned architecture owns common inference/provider routing, AI memory, context assembly, and reusable AI/research runtime capabilities when an application explicitly integrates them. The committed Phase 11 work prepares explicitly selected provider items; the current upstream working tree also has uncommitted shared-builder changes for assembling selected items into model input. Neither implements or automatically selects Shopping domain context: Shopping-specific providers and tools remain unavailable, and the future typed mutation-capability framework is not a Shopping integration today. This does not transfer Shopping's domain authority to Personal AI.

## Future data exchange

When a supported upstream transport and Shopping providers exist, Shopping → Personal AI context should be bounded, typed, and versioned. Each disclosed item should retain the appropriate owner/application/workspace scope, domain identity, source identity and version, source references and provenance, authority, freshness timestamps or expiry, sensitivity (including field-level labels where needed), and permission dependencies. Context selection should be explicit and bounded by fields, entity references, result count, bytes, and time.

Personal AI → Shopping changes should arrive as typed, versioned proposals or capability results. Shopping must perform owner/domain authorization, validate project revisions and hard constraints, enforce idempotency and any required user confirmation, persist the authoritative change, and return the resulting Shopping state. Personal AI must not write Shopping records directly.

Do not import Personal AI internal Python types into Shopping or create a shared package merely to align names. Agree on an external, versioned wire contract when an actual transport is available; map it inside Shopping's `PersonalAIClient` boundary.

## Related contracts

See the [Shopping integration contract check](../../apps/api/src/shopping/integrations/personal_ai/CONTRACT.md), [ADR 0003](../adr/0003-personal-ai-boundary.md), and `personal-ai-system/docs/personal-ai-chapter-2/02-target-architecture.md` in the sibling checkout for upstream details.
