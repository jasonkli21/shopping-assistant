# Product Roadmap

Implementation sequence and prerequisites: [Phase 0–9 plans and shared contracts](../planning/implementation-plans-index.md). For the live implementation boundary and acceptance status, use [`../current-state.md`](../current-state.md). Plans describe intended work and do not establish delivery or acceptance. Phase 2 and Phase 8 use local behavior because the Personal AI service has no verified structured-task or user-scoped memory contract.

The implementation roadmap is intentionally different from a marketing feature roadmap. Product growth should follow validated use cases rather than infrastructure ambition. Confirm the current authorized scope before starting a later phase.

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
