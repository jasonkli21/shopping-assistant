# Current implementation state — Shopping Assistant

Updated2026-10-14. This is the living delivery boundary. Code, contracts,
migrations and tests take precedence over plans. The stabilization patch is based
on `2268b944ffa8fe5c2e6f2787c88dea616160e398`; final commit/source identity and exact checks are recorded in the
[verification record](stabilization-2026-10-14.md). Independent final review and
external acceptance remain open.

## Implemented locally

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

## Verification and release boundary

Read [the local stabilization evidence](stabilization-2026-10-14.md) and
[suite verification](../../personal-ai-system/stabilization/VERIFICATION.md).
The all-five synthetic PostgreSQL/loopback HTTPS paths do not prove real IAM,
provider, cloud, browser or native-device behavior. Feature gates remain off by
default. No cloud deployment or live-provider operation was run. The user
authorized commits and pushes to remote main; hosted CI is separate evidence.

## Minimum context

Read [the router](README.md), the owning module/contract and focused tests.
[Suite contracts](../../personal-ai-system/stabilization/CROSS-REPO-CONTRACTS.md),
[operations](../../personal-ai-system/stabilization/OPERATIONS.md) and the
[review handoff](../../personal-ai-system/stabilization/REVIEW-HANDOFF.md) explain
cross-app assumptions and remaining acceptance. The
[previous status](history/stabilization/current-state-before-2026-10-14.md)
preserves detailed predecessor phase evidence and unresolved gates. This status
does not authorize implementation of the future roadmap.
