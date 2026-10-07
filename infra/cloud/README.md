# Cloud Infrastructure

Phase 9 local deployment assets and operator notes are in this directory and [`../../docs/deployment/runbook.md`](../../docs/deployment/runbook.md). Resource IDs and secret versions are intentionally supplied by the operator; no account-specific values are committed.

- [`web.env.example`](web.env.example) contains public Firebase web configuration placeholders only.
- `scripts/deploy_cloud_run.sh` deploys a reviewed image using exact operator-supplied project, region, service, origin, instance, and pinned secret-version settings.
- `scripts/deploy_firebase_hosting.sh` deploys the already-built SPA to an explicit Firebase project.
- `scripts/run_cloud_migration.sh` requires a direct database URL and an explicit backup/restore-point confirmation.

These assets do not establish a hosted deployment. Phase 6/8 predecessor gates and Phase 9 runtime/restore checks remain open.
