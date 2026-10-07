# Phase 9 — Cloud deployment and production hardening

Status: local implementation started; **not accepted**. This slice delivers the Phase 9 identity/configuration foundation, API container and Hosting configuration, owner export/purge, and operator documentation. It does not close the Phase 6 or Phase 8 gates, and the Phase 7 local execution decision still lacks production lifecycle evidence. Cross-instance generation ownership, hosted research/SSE verification, actual quota/billing configuration, and restore/security evidence remain open. See the [verification record](../deployment/phase-9-verification.md) and [runbook](../deployment/runbook.md). Cloud/provider capabilities and quotas must be checked against actual accounts at execution time.

## Outcome, slice and boundary

The authorized owner signs in on Firebase Hosting, creates a project backed by Neon PostgreSQL, completes the MVP journey through Cloud Run and can export/recover data. Another identity cannot access any private record; secrets remain server-side, costs and request/research limits are bounded, and restore is demonstrated.

Smallest production slice: production-mode container + authenticated project CRUD + migration on disposable Neon/staging DB + hosted SPA → authenticated API. Expand to verified SSE and full deterministic then credentialed research journey. Scope is a low-volume personal application; no multi-tenant marketplace/collaboration, Kubernetes, queue stack, major IaC hierarchy or speculative scaling. Cloud Run Jobs is deployed only if selected by Phase 7 evidence.

## Deployment and security contracts

Assets live in `infra/cloud/`, root local Compose remains for PostgreSQL only. Add API production Dockerfile with Python 3.12+, locked uv dependency install and a non-root runtime; exclude tests/.env/.git/local caches from context. Build SPA with pnpm lock and explicit public `VITE_API_BASE_URL`; SPA route rewrites in Firebase Hosting must serve `index.html` while preserving assets/cache behavior. Do not ship secrets into Vite variables.

Use explicit API origin with a documented narrow CORS allowlist for hosting/staging/local dev. Verify actual origin/OPTIONS/SSE behavior. A same-origin Firebase rewrite is optional only after current documented timeout/stream semantics are verified; do not rely on a rewrite hiding Cloud Run ownership/auth errors. Pin deployment region/account/project/resource IDs in nonsecret configuration, not code defaults that point at someone else's resources.

Neon URL has TLS enabled using verified current connection requirements; use SQLAlchemy's psycopg URL form. Application may use a pooled endpoint with small bounded pool/overflow/timeouts; migrations/admin/export use a verified direct connection. Compute aggregate maximum connections from per-instance pool × maximum instances plus jobs/migration allowance, compared with actual plan limit. No transaction held during provider or SSE I/O. Use Secret Manager references for DB credentials, Personal AI auth and Tavily keys; frontend contains only public Firebase configuration. Missing production secrets fail startup clearly without logging them.

Firebase Auth token verification is server-side (issuer, audience/project, signature, expiry). For the personal deployment allowlist a configured owner identity/UID; authentication alone does not authorize everyone with a Firebase account. Map UID to a stable `users`/owner UUID, with explicit one-time migration binding existing local-owner data to the chosen authorized identity. No arbitrary client owner assignment. Tests cover all projects, nested requirements, candidates, runs/jobs, products/offers/sources, claims, comparisons, decisions, messages/proposals, favorites, preferences and memory operations; foreign IDs return 404. Internal job runner uses verified service identity and cannot bypass owner/run authorization blindly.

Production configuration rejects local unauthenticated mode, wildcard credentialed CORS and debug details. Bind dev only to localhost when auth is disabled (document and adjust developer commands here). Browser uses short-lived bearer tokens; refresh through Firebase SDK. GET SSE must support authenticated fetch streaming rather than putting tokens in query strings/native EventSource URLs. Never log authorization headers or source URLs with embedded credentials. Handle expired token midstream/reconnect without duplicate command keys. Public `/health` is liveness only; add `/ready` with short DB reachability/schema-version check and no secret disclosure.

Retrieval defenses from Phase 4 are mandatory before cloud exposure: resolved destination/redirect/DNS protection, private/metadata blocks, content/byte/time ceilings, no arbitrary executable HTML in UI, safe outbound links and sanitization. Review dependency vulnerability reports separately with actual findings; do not claim an audit passed merely because packages installed. Enforce input sizes, provider deadlines, per-owner active limits and budgets server-side; no direct provider call from browser.

## Execution and streaming deployment decision

Select deployment topology explicitly from Phase 7, including conversation generation, not only research. Cloud Run request/CPU/process lifetimes cannot be treated as a durable background worker without verification.

For the local/simple branch, constrain deployment to the verified low-volume topology and ensure active bounded execution has a documented owner/lifetime and restart recovery. Prefer executing generation for the duration of the authenticated streaming request and persisting interruption/resume state; Phase 2 POST reserves the message command, first authenticated stream obtains a database lease and runs/attaches, repeated stream cannot generate twice. Update the Phase 2 implementation/contract in this phase if this ownership change is selected. Disconnect/cold shutdown must leave a resumable or clearly interrupted message, with explicit new retry key and no automatic double charge. A database-backed snapshot/poll response supports reconnect across instances; an in-memory map cannot be the production truth.

For long research selected for remote execution, dispatch Cloud Run Jobs by persisted run ID with Phase 7 leases/idempotency. For bounded research without Jobs, use a verified execution lifetime (request-held command/stream or explicitly supported instance CPU setting with lease/recovery), state its limitations, and test shutdown. Do not run unbounded detached `create_task` under request-only CPU allocation or pretend `max_instances=1` guarantees no overlapping revisions. Verify SSE proxy buffering/timeouts, heartbeats, disconnects and frontend fallback/history paths against actual deployed configuration.

## Ordered work packages

### 9A — Production config, identity and ownership migration

Add validated production settings/secret loading, auth/principal dependencies, owner identity mapping and data-binding migration/operator command with dry-run output. Build negative authorization tests for the entire API inventory and secure internal runner entry point. Preserve local fake development. Define environment-specific endpoints/allowed origins/public settings; review Personal AI authentication and avoid direct provider SDK usage.

### 9B — Containers, Hosting and reproducible staging deployment

Add Docker build/run instructions, `.dockerignore`, Firebase config/SPA rewrites and minimal deployment scripts that expose concrete resources/commands. Build reproducibly in CI without credentials. Use least-privilege Cloud Run/Jobs service accounts, Secret Manager access only to required secrets, authenticated service invocations where appropriate and bounded maximum instances/concurrency/request limits. No application image entrypoint runs migrations automatically.

Separate credentialed deployment workflow with explicit environment/secret requirements from normal CI. Implement migration as a single operator/release step: backup/restore point → direct DB connection → `alembic upgrade head` → `alembic check/current` → smoke → roll forward. Schema rollout uses expand/contract where old/new revisions overlap. Never downgrade a production DB reflexively or deploy destructive migrations without backup and concrete review.

### 9C — Runtime lifecycle, SSE, jobs and provider checks

Implement the selected verified execution branch above; test leases/restart across instances and stale workers. Configure actual timeouts/heartbeats and run deployed stream with token expiration/disconnect/reconnect. Selected Jobs branch gets real dispatch/start/retry/cancel/result checks. Verify Personal AI generation/structured task schemas, Tavily calls and retrieval access from Cloud Run; record quotas/access failures and no secret leakage. Optional memory remains disabled if Phase 8's live contract is unverified.

### 9D — Logging, metrics, limits and cost controls

Structured logs include request/run/job/owner pseudonymous IDs, durations, terminal codes and bounded tool/token/call counters; redact text/keys/tokens/URL credentials. Track errors, partial runs, retries, budget exhaustion, provider latency and spend estimates separately from billed totals. Configure provider quotas, run caps, active execution caps, max instances and billing alerts. Billing alerts notify; hard request/tool ceilings control spend. Set conservative defaults and verify the actual cloud limits rather than promising a fixed monthly cost.

### 9E — Export, backup/restore and privacy operations

Provide owner-scoped export containing projects/requirements, canonical variants/offers/observations, runs/attempts/source metadata/claims/evidence, assessment/comparison versions, decisions/notes/favorites and preferences/consent references. Exclude credentials and unnecessary raw provider pages. Include schema/export version and documented restore/import limitations. Decide retention for snapshots/excerpts/messages/logs; implement explicit owner-authorized purge of private rows and optional external memory retraction, retaining only necessary operational audit without deleted content.

Configure available Neon backup/restore policy based on the actual plan; if insufficient, add a simple scheduled/operator logical backup with encryption/access/retention and demonstrated restore. Restore into a disposable DB, run migrations/integrity queries and compare sample project/offer/provenance counts and journey. A download/export alone is not verified recovery. Document recovery point/time objectives appropriate to a personal app and actual measured restore result.

### 9F — Release verification and security review

Create `docs/deployment/runbook.md` with prerequisites, resource inventory, migration/deploy/rollback steps, secrets/auth settings, backup/restore, cost limits, provider outages and ownership binding. Create a deployed verification report with environment/date/revision, real commands/test outcomes and unresolved checks. Review auth/CORS/SSRF/logging/token handling/dependencies/container permissions and malformed/oversized requests. Resolve production blockers before calling launch complete.

Run staging deterministic-provider journey first, then an authorized live journey. Confirm Hosting deep-link reload, login/logout, forbidden identity, CRUD/reload, streaming, discovery→normalization→evidence→comparison→shortlist, partial provider failure, cancellation, export and restored DB. Check desktop/mobile/cold-start/error behavior. Promote the concrete reviewed artifact/config only within the user's deployment authorization; if actual account/credential/release authorization is unavailable, preserve scripts/runbook and label deployment unverified rather than claiming completion.

## Acceptance, commands and handoff

Offline `make validate`, PostgreSQL authorization/migration/export/runner tests, OpenAPI/type checks, previous evals/E2E and container build pass. Unit/CI tests cannot reach credentialed services. Add documented commands for `docker build`, local production-mode container smoke, SPA build, Firebase hosting deploy, Cloud Run deploy, migration step and optional Jobs deployment; use actual verified resource names/config in runbook, never runnable commands with imagined credentials/resources.

Production acceptance additionally requires actual signed-in/forbidden-user hosted tests, online Neon migration and restore evidence, real SSE/lifecycle verification, secret/log redaction, bounded configured cost/connection limits, actual Personal AI/Tavily/retrieval compatibility for the chosen launch capability and a completed security review. Unrun deployment/provider checks remain explicit blockers to a “production verified” claim. External memory and Jobs checks are required only if those capabilities are enabled.

Suggested commits: config/auth/owner migration; container/Hosting/release scripts; runtime lifecycle; metrics/limits; export/restore/privacy; verification/runbook/security fixes. Review: Can another signed-in user read any private ID? Can a deploy race orphan or duplicate work? Can the DB be restored? Are pooling/TLS/migration connections verified? Can limits fail closed? Are SSE credentials and logs safe? Is each claimed deployed capability actually checked?

Handoff: deployed resource/config inventory, owner binding, secret/auth contracts, selected execution topology, migration/export/restore runbooks, real verification evidence and remaining operational limits. Phase 10+ lifecycle/capture features require separate authorization and plans; do not begin them here.
