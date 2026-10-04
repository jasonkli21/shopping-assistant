# ADR 0003: Personal AI as an External Platform Boundary

## Status

Accepted.

## Decision

Integrate with `personal-ai-system` through a typed client/API boundary. Do not import its internal modules into this repository.

## Rationale

Shopping-specific domain logic should remain independently deployable while reusing generic model and memory capabilities from the broader personal-AI platform.
