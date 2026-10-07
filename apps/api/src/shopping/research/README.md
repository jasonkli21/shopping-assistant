# Research module guide

Research coordinates durable discovery and selected-product research. It owns run planning/execution state and the handoff to search, retrieval, catalog, and evidence services. Shopping projects remain authoritative for project requirements; a research run snapshots project revision, inputs, provider identity, and effective budgets.

## Module map

- `commands.py` validates and accepts run, retry, and refresh commands; snapshots context and effective budgets.
- `execution.py` owns run/query/attempt lifecycle transitions. `reads.py` builds owner-scoped run and candidate views. `common.py` contains shared normalization/validation helpers. `service.py` is the stable facade used by routers and orchestration.
- `task.py` and `product_task.py` build and validate AI planning/extraction contracts. `supervisor.py` coordinates discovery planning and run dispatch.
- `search_execution.py` handles discovery provider calls. `product_execution.py` orchestrates selected-product work; `product_persistence.py` records its stage outcomes and observations.
- `jobs.py` owns durable dispatch jobs, attempts, leases, recovery, and fencing. `executor.py` is the in-process `ResearchExecutor`; `runner.py` drains the same saved run ID for manual local recovery.

Keep provider calls behind `SearchProvider`, page retrieval behind `PageRetriever`, and work submission behind `ResearchExecutor`. Do not add a second research lifecycle or call model providers from this module.

## Durable ownership and recovery

The run row is the durable command and snapshot. A job row owns dispatch state; each claim creates a job attempt with a lease token. Heartbeats extend the lease, and writes from a stale token are fenced. Startup may recover expired leases; it does not take work from an unexpired lease. A manual runner uses the same ID-based claim path and cannot take over an unexpired lease. Treat ambiguous external calls as uncertain rather than blindly repeating a potentially charged operation. Cancellation settles the run/job and prevents late work from changing durable state.

The current execution choice is local and provisional. The [execution decision](../../../../../docs/architecture/research-execution-decision.md) records what is implemented and the missing runtime, restart, and provider measurements; it is not a production suitability approval.

## Budgets, targeting, and retries

Every accepted run snapshots its effective query, result, candidate, source, page, byte, AI-call, and deadline limits. Quick mode uses a smaller fixed envelope (currently three queries, one selected product, two sources per product, four pages, and a 45-second deadline); deep mode uses configured server limits, which client input may lower but not raise. Exact caps and freshness thresholds live in `commands.py` and the execution decision, not here.

Product research snapshots requested source classes/domains and freshness needs. Planning uses freshness to prioritize missing or stale evidence and offers; it does not guarantee source independence or evidence quality. Search retries are bounded by the saved attempt budget and run deadline. Retrieval and AI failures have their own stage outcomes; do not infer a retry policy broader than the implementation and phase evidence establish.

## Where to verify changes

- API lifecycle and behavior: `apps/api/tests/research/`.
- Persistence, migration, and concurrency behavior: `apps/api/tests/db/` and the database-marked research cases.
- Planning and evidence boundaries: `apps/api/tests/evals/intent/`, `discovery/`, `evidence/`, and `preferences/`.
- Relevant decisions/plans: [`docs/planning/phase-7-implementation-plan.md`](../../../../../docs/planning/phase-7-implementation-plan.md), [`docs/architecture/research-execution-decision.md`](../../../../../docs/architecture/research-execution-decision.md), [`docs/architecture/research-evidence.md`](../../../../../docs/architecture/research-evidence.md), and [`docs/architecture/data-model.md`](../../../../../docs/architecture/data-model.md).

PostgreSQL lease, concurrency, restart, and recovery checks plus browser and quality/call-count verification remain open in the current phase record. Do not treat deterministic tests or a phase plan as evidence those gates passed.
