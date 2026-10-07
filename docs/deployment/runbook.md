# Cloud deployment runbook

Status: **implementation guide only; no cloud resources have been configured or deployed.** Resource IDs, quotas, secret versions, backup policy, and hosted behavior must be recorded from the actual accounts before use. This runbook does not pass the Phase 6 or Phase 8 gates.

## Release boundary

Do not expose the complete shopping journey until these blockers are closed:

- Phase 6 PostgreSQL migration/integration and deterministic browser journey gates remain open.
- Phase 8 independent review has unresolved lifecycle, preference validation, transaction, privacy, and prompt-contract findings. See the [Phase 8 handoff](../planning/phase-8-independent-review-handoff.md).
- Phase 7 chose bounded in-process, ID-based research. Cross-instance conversation generation ownership, reconnect behavior, shutdown/restart, and deployed SSE semantics have not been verified for Cloud Run. `--no-cpu-throttling` preserves CPU while an instance is active but does not make in-process work durable.
- The checked Personal AI contract has no structured shopping task endpoint. Production mode refuses deterministic fake generation, but the current external adapter reports `provider_unavailable`. Do not claim an assistant journey until a compatible upstream contract and implementation are verified.
- Neon plan connection limits, backup/restore behavior, Cloud Run quotas, provider quotas, and billing alerts have not been checked for a real account.

## Resource inventory to record

| Resource | Actual value | Owner / notes |
|---|---|---|
| Google Cloud project ID and billing account | Fill from account | |
| Cloud Run region, service, image digest, service account | Fill from deployment | |
| Firebase project ID, web app ID, Hosting site and allowed domain | Fill from Firebase | |
| Firebase owner UID | Fill after account setup; do not use email as identity | |
| Neon project, branch, database, app role, pooled endpoint and direct endpoint | Fill from Neon | |
| Secret Manager names and pinned versions | Fill from Secret Manager | |
| Tavily key quota and alert owner | Fill from provider account | |
| Run max instances, concurrency, timeout, CPU/memory and billing alert | Fill from verified quota/config | |
| Neon connection limit and calculated aggregate maximum | Fill from selected plan | |
| Backup policy, restore point, retention and measured restore result | Fill after restore exercise | |

Never commit connection strings, provider keys, Firebase private keys, service-account JSON, database dumps, or generated local `.env` files.

## Identity and application configuration

1. Create or select the Firebase project and register its web app. Enable the intended sign-in provider in Firebase Authentication. The UI currently supports email/password sign-in.
2. Record the Firebase project ID and the owner's immutable Firebase UID. Configure `FIREBASE_PROJECT_ID`, `FIREBASE_OWNER_UID`, and the existing stable `LOCAL_OWNER_ID` on the API. The server verifies Firebase ID tokens and accepts only that one UID; it does not authorize every signed-in Firebase account.
3. Give the Cloud Run service identity only the Secret Manager access required for the selected database and Tavily secret versions. Enable the Firebase Authentication / Identity Toolkit API in the Firebase project and grant the service identity `firebaseauth.users.get` there so `check_revoked=True` can look up user status. Prefer a custom role containing only that permission; `roles/firebaseauth.viewer` is the narrower predefined fallback. Firebase Admin uses the Cloud Run service identity through Application Default Credentials; no service-account key belongs in the image or frontend. See [Firebase Authentication IAM permissions](https://docs.cloud.google.com/iam/docs/roles-permissions/firebaseauth) and [Admin SDK setup](https://firebase.google.com/docs/admin/setup).
4. Build with `VITE_API_BASE_URL` set to the explicit HTTPS Cloud Run origin and the public `VITE_FIREBASE_*` web configuration. Those Vite values are public Firebase client configuration, not server secrets. Do not set a secret in any `VITE_*` variable.
5. Set `CORS_ORIGINS` to the exact Firebase Hosting origin(s). Production rejects wildcard origins and credentialed CORS. The browser sends short-lived Firebase bearer tokens in normal API requests and authenticated `fetch` streams; tokens never go in query strings.

The API keeps `/health` as liveness. `/ready` checks PostgreSQL, the Alembic head and the configured owner binding; it returns no connection or secret details.

## Database setup and owner binding

Use a Neon pooled endpoint for the application and a verified direct endpoint for migrations, owner binding, and backup/restore. Use SQLAlchemy's `postgresql+psycopg://` URL form with TLS (`sslmode=require` or stronger). Do not assume a Neon limit from a plan name; inspect the actual project and endpoint settings.

Before release, calculate:

```text
application max = (instances in each concurrently active revision × (DB_POOL_SIZE + DB_MAX_OVERFLOW))
                  + migration/admin connections
                  + any enabled job connections
```

The default application pool is 2 connections with no overflow per instance. Include overlapping old/new revisions and manually run tools in the Neon limit. Lower Cloud Run max instances or pool sizes if the verified limit requires it. Cloud Run max instances is a cost/connection bound, not a lock against overlapping revisions.

1. Create an encrypted Neon backup or provider restore point and record its ID/time.
2. Configure the direct `MIGRATION_DATABASE_URL` in a protected operator environment. The Cloud Run runtime does not receive it.
3. Run the ordered migration step. It refuses to proceed until the operator explicitly confirms a usable backup/restore point:

   ```bash
   MIGRATION_DATABASE_URL='postgresql+psycopg://…?sslmode=require' \
   BACKUP_RESTORE_POINT_CONFIRMED=yes scripts/run_cloud_migration.sh
   ```

   The script runs `alembic upgrade head`, `alembic check`, then `alembic current`. It never runs from the application image entrypoint.
4. Bind the configured Firebase UID to the existing local owner UUID. The first command is a dry run and reports only row counts and the owner UUID. Apply only after checking that the UID and owner UUID match the release record:

   ```bash
   cd apps/api
   MIGRATION_DATABASE_URL='postgresql+psycopg://…?sslmode=require' \
   FIREBASE_OWNER_UID='the-configured-uid' \
   LOCAL_OWNER_ID='the-existing-owner-uuid' \
   uv run --locked python -m shopping.accounts.bind_owner --firebase-uid 'the-configured-uid'

   # Repeat with --apply after reviewing the dry-run output.
   uv run --locked python -m shopping.accounts.bind_owner --firebase-uid 'the-configured-uid' --apply
   ```

The binding command refuses pooled Neon hosts, a UID outside the configured allowlist, an existing conflicting mapping, or an unconfigured direct database URL. Binding reuses the stable owner UUID already stored on local records; it does not rewrite private rows.

## Build and deploy

Build the API image from the repository root so the lockfile and source are in the context. The Docker build uses Python 3.12, locked uv dependencies, excludes tests and local secrets, and runs as UID 10001. It listens on Cloud Run's `PORT`; it does not run migrations.

```bash
IMAGE='verified-region-docker.pkg.dev/verified-project/verified-repository/shopping-api:REVIEWED_REVISION' \
  docker build --file apps/api/Dockerfile --tag "$IMAGE" .
```

Use an immutable image digest for deployment and record the digest, source revision, and build result. A credential-free CI build is defined in `.github/workflows/ci.yml`; it does not deploy.

The deployment script requires real project, region, service, service-account, quota, exact CORS origin, and pinned Secret Manager version values. Do not copy placeholder values from examples. It creates a public Cloud Run ingress endpoint because Firebase bearer tokens are application credentials rather than Cloud Run IAM credentials; all private routes still require a verified owner token. Only `/health` and `/ready` are unauthenticated. The attached service identity needs read access only to the secrets selected by the release.

```bash
scripts/deploy_cloud_run.sh
```

The script sets min instances to zero, bounds max instances and per-instance concurrency, pins database/provider secret versions, and disables CPU throttling so bounded in-process work is not paused while an instance is active. This incurs CPU billing while active and does not prove work survives shutdown. Verify current timeout, SSE buffering, disconnect, and instance lifecycle behavior before using research or generation on the hosted service.

For Hosting, build with explicit public settings, then deploy the site to the selected Firebase project:

```bash
set -a
source infra/cloud/web.env.example # replace every placeholder in a protected environment file first
set +a
scripts/build_cloud_web.sh
FIREBASE_PROJECT_ID='verified-project-id' scripts/deploy_firebase_hosting.sh
```

Firebase Hosting serves existing static assets first and rewrites unmatched SPA routes to `index.html`; hashed `/assets/**` files are immutable-cacheable and `index.html` is not cached. The API remains on its explicit Cloud Run origin. A Hosting-to-Cloud-Run rewrite is not configured; add one only after actual timeout, stream, origin, and authentication behavior is verified.

## Backup, restore, export, and purge

Neon provider backup/restore availability depends on the actual plan. Verify its retention and restore-point behavior in the account. An operator logical-backup alternative uses `pg_dump` over the direct TLS endpoint and encrypts output with `age` before writing it. Configure the host's PostgreSQL client and `age` in advance:

```bash
PGHOST='verified-direct-host' PGPORT=5432 PGDATABASE='verified-db' PGUSER='backup-role' \
PGPASSWORD='loaded-from-a-secret-manager' PGSSLMODE=require \
BACKUP_DIR='/protected/backup/path' BACKUP_AGE_RECIPIENT='age1…' \
scripts/backup_neon.sh
```

The backup script uses restrictive file permissions, a caller-selected encryption recipient and retention days. Store backups only in an encrypted, access-controlled destination. Do not paste passwords into shell history. Schedule it only on a trusted operator host after verifying the chosen storage and retention policy.

Restore a backup to a disposable database or Neon branch, never over the live database by default. Decrypt to a pipe and use `pg_restore --no-owner --no-acl` with a separate restore role. Then apply migrations, run integrity queries, compare project/offer/source/claim/evidence counts, and exercise one restored project journey. Record measured restore time and the timestamp of the latest recoverable backup. An export download is not a database restore.

`GET /account/export` returns a bounded versioned JSON export of owner-scoped shopping rows and child records. It excludes Firebase UID bindings, privacy audit, and full retrieved source text; it retains claim/evidence excerpts and source metadata, redacting credentials from URL fields. The HTTP path is capped at 2,000 records and 10 MiB and is not an import format. For a complete export beyond those limits, run the operator command against the verified direct TLS endpoint; it creates a new mode-0600 file and refuses to overwrite an existing path:

```bash
cd apps/api
MIGRATION_DATABASE_URL='postgresql+psycopg://…?sslmode=require' \
  uv run --locked python -m shopping.accounts.privacy \
    --owner-id 'the-existing-owner-uuid' --mode export \
    --output '/protected/export/shopping-owner.json'
```

`DELETE /account/data?confirm=DELETE_MY_DATA` deletes owner-scoped application rows and the Firebase UID binding, retaining only a timestamped audit row with pre-delete per-table counts and no deleted content. The HTTP path is limited to 2,000 rows per operation. For larger owners, the operator workflow applies the same write fence and full transactional deletion without the HTTP cap:

```bash
cd apps/api
MIGRATION_DATABASE_URL='postgresql+psycopg://…?sslmode=require' \
  uv run --locked python -m shopping.accounts.privacy \
    --owner-id 'the-existing-owner-uuid' --mode purge --confirm DELETE_MY_DATA
```

The operator export and purge use a direct TLS endpoint and the owner UUID from the release record. After purge, the configured UID must be bound again by an operator before the owner can use private routes. Optional external memory is disabled; there is no external memory data to retract.

## Staging verification and release record

Use a disposable Neon database and deterministic fake providers first. Record exact environment, revision/image digest, commands, outputs, and dates in `docs/deployment/phase-9-verification.md`. Then, only with configured account credentials, verify:

- Firebase login/logout, owner token acceptance, foreign Firebase identity denial, and revocation/expiry behavior.
- Foreign project, requirement, candidate, run/job, product/offer/source, claim/evidence, comparison, decision/note/favorite, preference and memory IDs all return 404 and expose no private data.
- Deep-link reload, mobile/desktop layout, authenticated API origin/OPTIONS, and authenticated fetch-based SSE.
- CRUD/reload, deterministic research, evidence/citations, comparison/shortlist, partial provider failure, cancellation, export and purge.
- Process restart, concurrent requests/revisions, leases, stale-worker fencing, request timeout, SSE heartbeat/buffering/disconnect/reconnect, and duplicate-command behavior on the actual service configuration.
- Backup/restore into a disposable database, migrations, integrity counts, and the restored journey.
- Secret references and IAM, structured log redaction, malformed/oversized requests, SSRF protections, dependency reports, max instances/concurrency, provider limits, and billing alerts.

Keep unrun checks open. Promote only the reviewed image/config after the predecessor gates and hosted evidence are closed.
