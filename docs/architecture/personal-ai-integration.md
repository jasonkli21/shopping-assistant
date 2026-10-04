# Personal AI Integration

## Boundary

The Shopping Assistant is a specialized domain application. The separate `personal-ai-system` is the shared intelligence platform.

Use a typed HTTP client boundary represented in this repo by `PersonalAIClient`.

Do not import internal code or database structures from the personal-AI repository.

## Shopping owns

- shopping-specific prompts/task definitions;
- product and project schemas;
- structured mutation semantics;
- research planning for shopping;
- product comparison logic;
- evidence interpretation;
- shopping preference lifecycle.

## Personal AI owns

- model/provider invocation;
- generic generation and streaming;
- user-wide memory;
- model configuration/cost controls;
- generic reusable research primitives when they truly become shared.

## Expected API evolution

Conceptually, the client may expose capabilities such as:

```text
generate(...)
stream(...)
retrieve_context(...)
propose_memory(...)
```

Possibly later:

```text
research(...)
```

Do not design shopping features around methods that the personal-AI system does not yet expose. Use adapters/fakes until contracts are available.

## Preference promotion

A project-specific preference such as “this chair must fit under a 27-inch desk” should remain local to the project.

A possible long-term preference such as “prefers compact furniture” may become a `PreferenceCandidate` and be explicitly promoted or proposed to personal-AI memory.

Avoid silently turning one shopping decision into permanent memory.

The current Phase 0 client implements only `generate` with minimal dictionary envelopes and an echo fake. Streaming/task validation arrives in Phase 2; memory methods are conditional on the verified external API in Phase 8. Conceptual methods above do not assert external service availability.
