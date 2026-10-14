# Shopping Assistant stabilization evidence — 2026-10-14

Base revision: `2268b944ffa8fe5c2e6f2787c88dea616160e398`. This record covers the committed stabilization patch,
including earlier Luna changes reconciled by direct implementation QA. Independent
final review is intentionally owned by a separate session.

Shopping owns projects, constraints, discovery, catalog/evidence, comparisons,
shortlists, preferences, proposals and research jobs. Checkout/payment remain
outside scope. General external AI generation and the Shopping sidecar remain
unavailable. Existing Phases6–9 acceptance gates remain open.

The default-off delegated destination now supports `project.set_budget` and
`project.append_context_note` through the normal project command service. An
owner/execution receipt and effect commit atomically at migration
`p9_delegated_task_receipts`. Retired fingerprints can observe known exact
receipts; unknown contracts cannot create writes. Current linked identity,
owner lifecycle, revision, constraints and PAI confirmation/grant authority are
rechecked. Receipts survive project deletion and participate in owner erasure.
The new migration refuses populated rollback. The existing preference cycle is
declared with a separate metadata DDL edge; database FK semantics stay intact.

Baseline fixes include the explicit container Alembic path, timestamp handling,
bounded-response fixture, and Discover's derived initial goal. The full current
API/web/native evidence is in the linked verification record. No container,
live provider, cloud IAM, hosted lifecycle or new browser acceptance is inferred.

Fresh CI exposed missing local environment/auth in the one-shot container
Alembic smoke. The migration invocation now sets both explicitly; production
security validation is unchanged.

## Evidence authority

[Exact commands/counts/source identity](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/VERIFICATION.md),
[transition verification](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/LUNA-TRANSITION-VERIFICATION.md)
and [review priorities](https://github.com/jasonkli21/personal-ai-agent/blob/main/stabilization/REVIEW-HANDOFF.md)
are the suite evidence index. Earlier records retain their original date/results;
newer local evidence supersedes their unrun-local-check statements only.

No personal records were used or deleted. Local tests created disposable databases
and synthetic private-store directories. Root-owned test processes are stopped at
handoff. Credentials, private payloads and unrelated user files are excluded from
commits. Cloud/provider/device/hosted CI acceptance cannot be inferred from this
local patch, and erasure does not independently invalidate previously downloaded
exports or historical cloud backups.
