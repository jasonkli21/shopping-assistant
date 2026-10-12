# ADR 0003: Personal AI as an External Platform Boundary

## Status

Accepted.

## Decision

Integrate with `personal-ai-system` through a typed client/API boundary. Do not import its internal modules into this repository.

## Rationale

Shopping-specific domain logic should remain independently deployable while reusing generic model and memory capabilities from the broader personal-AI platform.

## 2026-10-11 amendment — read-only context contract

Shopping owns `shopping-context-read-v1` at `/v1/integrations/personal-ai/context`. It is an additive read-only projection over Shopping's canonical PostgreSQL store; it does not replace the app-owned `PersonalAIClient` generation boundary or authorize Personal AI writes. The request carries `project_id` as a Shopping entity reference and always uses `workspace_id = null` until a separately accepted mapping exists.

The context integration defaults off in both services. Shopping verifies the Personal AI service token and delegated Google user token independently, maps the exact configured Google subject/email to the fixed Firebase owner, and checks owner/project authorization before retrieval. A mapping-version label and the exact identity configuration are fingerprinted into read permission dependencies, so changing the mapping invalidates prior context. This is deployment configuration for the fixed single-owner model, not a multi-owner grant store. Project context is authoritative; persisted offers and research claims remain freshness-bearing external observations. `shopping.product_action` stays unavailable until the typed mutation work is accepted. Task generation and the shared sidecar remain incomplete while their identity, routing, and host contracts are absent.
