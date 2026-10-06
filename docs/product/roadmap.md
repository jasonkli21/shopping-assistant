# Product Roadmap

Implementation sequence: [Phase 0–9 plans and shared contracts](../planning/implementation-plans-index.md). Phase 0 foundation, Phases 1–5 and their accepted workflows, and Phase 6–8 local code are present. Phase 6's mandatory review gate remains open; Phase 7 and Phase 8 are not accepted because required PostgreSQL/browser checks remain unrun. Phase 9 remains planned. Each phase is implemented/reviewed separately. Phase 2 and Phase 8 use local behavior because the Personal AI service has no verified structured-task or user-scoped memory contract.

The implementation roadmap is intentionally different from a marketing feature roadmap. Product growth should follow validated use cases rather than infrastructure ambition.

## MVP capability set

By the end of Phase 6:

> Need → Requirements → Discovery → Research → Comparison → Shortlist

must work coherently end to end.

## Post-MVP themes

### Research quality

- deeper multi-source research;
- refresh/staleness controls;
- targeted source strategies;
- long-running jobs only if needed;
- better source-quality interpretation.

### Personalization

- project-specific versus persistent preferences;
- explicit preference promotion;
- prior purchase context;
- connection to personal-AI memory.

### Product lifecycle

- price history and alerts;
- new-model detection;
- purchase recognition;
- ownership/warranty history;
- replacement recommendations.

### Capture and discovery

- browser extension;
- share sheet;
- image/visual search;
- saved external product links.

### Cross-application context

- travel-specific shopping needs;
- finance/budget awareness;
- email receipt/purchase extraction.

These should not drive the initial schema beyond preserving clean extension points.
