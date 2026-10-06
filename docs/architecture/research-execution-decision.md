# Research execution decision — 2026-10-05

## Decision

Keep research execution local and ID-based. The API persists a run and its initial job before returning `202`; a lifespan-owned in-process executor dispatches the saved run ID to the shared runner. The manual runner uses the same job claim and workflow path:

```bash
cd apps/api
uv run python -m shopping.research.runner --run-id <RESEARCH_RUN_UUID>
```

Claims use a 60-second lease with a 20-second heartbeat. App startup recovers only expired leases and dispatches queued jobs. A manual invocation cannot take over an unexpired lease. Lease tokens fence stale workers from committing research state. Individual search calls have a bounded retry policy; uncertain in-flight provider calls are retained as uncertain rather than repeated blindly.

## Evidence and limits

No representative or worst-case provider durations, disconnect measurements, deployment lifecycle measurements, or completed Phase 6 latency/quality measurements are available in this checkout. Live provider credentials are unavailable, and the Phase 6 repository gate remains open because its PostgreSQL and browser journey checks are outstanding. The implementation therefore does not establish that local execution meets a measured service window.

There is no evidence that a run exceeds the configured maximum deadline (60 seconds by default; 45 seconds in quick mode), or that a deployment lifecycle cannot safely finish or recover a run. That is insufficient evidence to justify a remote execution system. Cloud Run Jobs remains a later conditional option if measurements show that the local runner cannot meet an explicit reliability or execution-window requirement. No queue, broker, or remote adapter is added.

## Bounded behavior

The selected local branch persists effective per-run budgets and snapshots mode, source targets, freshness needs and refresh lineage. Quick mode caps research at three queries, ten candidates, twenty results, four attempts, one product, two sources per product, four pages, 600,000 retrieved bytes, six AI calls, an 8,000-character output and a 45-second deadline. Deep mode uses configured server limits (defaults include a 60-second deadline, 15-second provider timeout and two concurrent runs); client requests may only lower configured budgets. Search retries are limited to two retries per query, an eight-second delay ceiling, the run deadline and the run attempt budget.

## Unverified

- PostgreSQL execution of migrations `0015`–`0018`, including downgrade/re-upgrade, backfill behavior and concurrent lease claims.
- Process restart, late-worker fencing and recovery against a live PostgreSQL instance.
- Provider-specific retry timing, quota behavior and actual run duration/cost.
- Browser journey for progress, retry, cancellation, source targeting and offer history.
- Quality/call-count comparison against the Phase 5/6 labeled fixtures.

This decision records the implementation branch only. It is not a production deployment approval and does not close the Phase 6 gate.
