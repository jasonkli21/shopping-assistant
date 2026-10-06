# Phase 7 — Research quality and durable orchestration

Status: implemented locally at the user's explicit direction while Phase 6's repository-wide gate remains open. This does not pass or waive that gate. Read the [index](implementation-plans-index.md), [Phase 6 review](phase-6-review.md), [validation record](../../VALIDATION.md), and [executor decision](../architecture/research-execution-decision.md). Quality measurements and PostgreSQL/browser verification remain incomplete.

## Outcome, slice and boundary

The user chooses quick or deep research, targets missing evidence and requests refresh of stale offers/claims. Work survives a retry/restart as inspectable durable jobs without duplicate facts/charges where preventable. Smallest slice: one product refresh job → transient failure → bounded retry → successful new observations → preserved prior history and refreshed assessment.

Scope: quality modes, source targeting, freshness-based planning, durable job states, attempt budgets, explicit retry/cancel/recovery and a conditional executor change. Exclude queues/schedulers, recurring alerts, generalized DAG engine, mass crawling, new search providers without evidence, global knowledge graph and blanket browser automation. Remote jobs are a branch gated by measurements, not an unconditional acceptance criterion.

## Stable contracts and migrations

Reuse `research_runs`, input snapshots, source/claim/offer idempotency and stage attempts. Add `research_jobs`: UUID, run FK, stage type (`plan|search|retrieve|extract|assess|refresh_offer`), target/serializable payload schema version, queued/running/succeeded/failed/canceled state, attempt_count/max_attempts, not_before, lease owner/token/expiry, heartbeat and terminal times, sanitized error. Add job attempts with start/end/provider metadata/budget consumption; existing attempts migrate/link without fabricating jobs for completed old runs. Jobs depend on a small persisted prerequisite set or a deterministic stage sequence; avoid a reusable graph scheduler.

Use PostgreSQL claim/lease transaction (`SELECT … FOR UPDATE SKIP LOCKED` where concurrent claiming is required). Each claim obtains a fencing token; late or expired workers cannot overwrite a newer attempt's final state. Persist job result/observation references before terminal success, with uniqueness keys inherited from Phases 3–5. A crashed worker's lease expiry permits bounded reclaim; no lease opens a long DB transaction. Retry transient timeouts/rate limits/selected 5xx with bounded exponential delay/jitter (seed/clock injectable in tests); malformed/auth/permission/unsupported-page failures are terminal until configuration/user changes. Count failures/retries against run time/tool/cost budgets. Respect provider Retry-After within deadline/ceiling.

At-least-once execution cannot guarantee exactly-once external billing. Persist attempt intent before I/O and provider request IDs after response, use provider idempotency only if verified, and mark uncertain charged attempts after crash. Do not retry uncertain expensive calls without available budget/policy. Cancellation revokes claim/completion authority; data already committed stays inspectable. Run completion is derived from required jobs: succeeded, partial, failed or canceled; optional unavailable evidence produces warnings/unknowns.

Evolve `ResearchExecutor` from closure execution to a serializable dispatch contract such as `submit(ResearchExecutionContext(run_id)) -> ExecutionReceipt`; runner loads run/jobs by ID. The in-process adapter and optional remote adapter use the same job runner. Update all Phase 3/5 callers and fakes once; do not keep parallel executor families. Conversation generation remains its own lifecycle, but shared application supervisor/ownership rules must be documented for later multi-instance deployment.

Modes snapshot effective limits: quick prioritizes identity/current offers and existing validated evidence; deep seeks missing requirement dimensions and multiple independent source classes within higher bounded limits. No unlimited mode. Source targets specify allowed class/domains and exclude duplicate syndication; user requests cannot bypass retriever security. Refresh offers independently from specifications/community claims. Reuse unchanged content hashes/validated extraction where task version matches, but create a new retrieval observation and assessment context as needed. Manual catalog corrections and user judgments survive refresh.

## Ordered work packages

### 7A — Baseline quality audit and bounded mode design

Use Phase 6 fixture/live measurements to identify failure/source gaps and latency. Define quick/deep budgets and expected source coverage for the existing category eval cases. Record why each additional step improves a concrete requirement and how cost is bounded. Extend planning schemas with dimensions/source targets/freshness needs; no opaque “deep agent.”

### 7B — Durable jobs and safe runner

Migrate jobs/attempts, implement claim/lease/fencing/cancel/retry state machine and ID dispatch. Test two claimers, expired worker, restart mid-stage, duplicated callbacks, uncertain provider completion, canceled worker finishing late and partial dependencies. Use deterministic clock/backoff and fake providers; preserve completed Phase 3–6 runs. Add manual local drain command (e.g. `uv run python -m shopping.research.runner --run-id ...`) and document exact invocation. Run recovery on app startup only for expired ownership, not all other instances' running jobs.

### 7C — Refresh and targeted research slice

Add commands to request mode/targets and refresh selected data. New run references original run/observations and current project/catalog revisions. Refresh cannot overwrite manual identity corrections or change decisions. Test stale offers/fresh specs, unchanged source, missing page, new contradictory evidence, task-version invalidation and requirement edits during refresh. Old comparison snapshots remain readable/stale until explicit regeneration.

### 7D — Research quality UX/evaluation

Research page exposes mode limits, per-job progress/attempts/warnings, queued/running/partial/failed/canceled and explicit retry/refresh. Distinguish pending retry from completed research with unknown evidence. Show latest observation versus previous history and enable source targeting without exposing vendor payloads. Test offline scheduling delays, retry/cancel, hidden-tab polling and mobile progress. Compare quality against labeled Phase 5/6 fixtures; require no grounding/identity regression and report added coverage and call counts.

### 7E — Remote execution decision gate (conditional)

Write `docs/architecture/research-execution-decision.md` with measured representative and worst-case durations, disconnect/restart behavior, interactive request budget and a concrete reliability requirement. Keep ID-based in-process/manual runner when it meets local needs. Choose Cloud Run Jobs only if observed runs outlast the acceptable execution window or deployment lifecycle cannot safely finish/recover them. No arbitrary latency benchmark implies infrastructure by itself.

If justified, add a thin adapter in `research/`/`integrations/` using persisted run ID, shared runner and explicit credentials contract; mocked dispatch tests stay offline. Infrastructure deployment waits for Phase 9 unless explicitly supplied here. Test duplicate dispatch, dispatch failure, job restart/cancel and receipt/status reconciliation. Do not introduce Redis/Celery/PubSub/Cloud Tasks just to trigger jobs. If real remote tests cannot run, remote branch remains unverified and may not be selected for production yet.

## Acceptance and verification

A failure/retry/refresh slice preserves prior provenance and creates no duplicate normalized offers/claims for the same observation/task. Concurrent/expired workers cannot corrupt state; budgets include retries/uncertain attempts. Manual corrections/notes/decisions survive refresh. Quick/deep behavior is bounded, explainable and fixture-evaluated. The executor has one ID-based contract. The remote decision report has evidence and explicitly chooses local or conditional remote; no distributed system is required to pass the local branch.

Run `make validate`, PostgreSQL job/concurrency/recovery/migration tests, existing E2E plus retry/refresh E2E, OpenAPI/types check and research-quality evals. Test seeded prior-phase DB upgrade/metadata. Run local runner restart and duplicate claim scenarios with fakes. Separate live/provider quota/backoff and remote execution checks require opt-in credentials; record actual attempts/timing/cost and gaps.

Suggested commits: audit/modes; jobs/runner/executor evolution; refresh semantics; UX/evals; conditional remote adapter/decision; evidence docs. Review: Are retryable and permanent failures distinct? Can expired workers commit? Is billing uncertainty honest? Are freshness classes separate? Does deeper research improve evidence instead of just call count? Is remote execution concretely justified?

Handoff: serializable execution IDs, durable job/lease/attempt semantics, refresh/version rules, mode budgets, runner command, quality measurements and executor decision. Phase 8 reads shopping context without taking over orchestration; Phase 9 deploys the selected execution branch and resolves multi-instance conversation lifecycle. Remaining external gaps: actual provider retry semantics and any selected Cloud Run Jobs dispatch/runtime verification.

## Local implementation record — 2026-10-05

The code slice is implemented, but Phase 7 is **not marked accepted**: the Phase 6 gate is still open, and the plan's database/concurrency, browser, provider and labeled-quality checks were not run in this turn.

Implementation commits: `0f6b708` (API, persistence, execution and refresh behavior) and `22c4e3b` (frontend and generated API types). The current documentation update is committed separately.

| Work package / acceptance area | Implementation | Evidence in this turn | Remaining gap |
|---|---|---|---|
| 7A bounded modes, source targeting and freshness | `research/commands.py`, `research/schemas.py`, `research/product_task.py`, `research/product_execution.py`; quick/deep caps and snapshotted source/domain/freshness targets | API schema generation/check passed; static lint and type checks recorded in `VALIDATION.md` | No Phase 6 measurement baseline or labeled quality/call-count comparison; budgets are bounded defaults, not measurement-derived quality claims |
| 7B persisted jobs, ID executor, lease fencing, cancellation and restart recovery | `research/models.py`, `research/jobs.py`, `research/executor.py`, `research/supervisor.py`, `research/runner.py`, `research/execution.py`; migrations `0016`–`0017` and active-run backfill in `0016` | `alembic upgrade head --sql` generated through `0018`; Ruff check/format and TypeScript checks passed | SQL was generated, not applied. Claim contention, crash/restart, expired worker, uncertain external completion and late-write behavior remain unverified against PostgreSQL |
| 7C targeted refresh and preserved observations | `research/product_execution.py`, `research/product_persistence.py`, catalog/evidence models and reads; migration `0018`; refresh lineage and safe existing-variant matching | API types generated and `--check` passed | Offer/claim refresh, manual-correction preservation and prior-history behavior have not been exercised against PostgreSQL or browser flows |
| 7D progress and actions | `DiscoverPage.tsx`, `ProductResearch.tsx`, API client/types and styles expose modes, job/query attempts, retry timing, cancellation, retry and offer status/history | TypeScript project build check passed | Interaction, mobile, hidden-tab polling and browser E2E checks not run |
| 7E execution decision | [Research execution decision](../architecture/research-execution-decision.md) selects the shared local ID-based runner and records why remote execution lacks evidence | No duration or deployment-lifecycle measurements exist to justify a remote adapter | The local branch's real duration/reliability suitability is unmeasured; Cloud Run Jobs remains conditional |

The request explicitly selected Phase 7 despite the documented Phase 6 prerequisite. Implementation proceeded without changing Phase 6's status. Do not treat generated SQL, deterministic fakes, static checks, or this implementation record as a passed Phase 6 or Phase 7 integration gate.
