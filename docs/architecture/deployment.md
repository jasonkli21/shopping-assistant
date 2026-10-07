# Deployment Architecture

## Local development

```text
PostgreSQL 16  → Docker Compose
FastAPI        → uv / local process
React/Vite     → pnpm dev / local process
```

Do not containerize every local process by default; direct execution improves reload/debugging.

## Cloud target

```text
Firebase Hosting
      │
      ▼
Google Cloud Run ──────► personal-ai-system
      │
      ├───────────────► external search/web
      │
      ▼
Neon PostgreSQL
```

Secrets move from local `.env` files to Google Secret Manager.

The local Phase 9 baseline uses Firebase Authentication for browser sign-in and server-side Firebase Admin SDK token verification. The API authorizes one configured Firebase UID and maps it to the pre-existing stable owner UUID. See the [cloud runbook](../deployment/runbook.md) for deployment boundaries, direct migration connection, secret handling, export/purge, and the unverified runtime/restore gates.

## Why GCP + Neon

- aligns compute with the existing personal-AI deployment direction;
- keeps the shopping domain on standard PostgreSQL;
- supports scale-to-zero patterns for a low-volume personal app;
- avoids paying for always-on database infrastructure during early development.

## Background research

Define the research execution boundary early, but start with `InProcessResearchExecutor`.

If real research operations become too long for interactive request handling, add a Cloud Run Jobs adapter. Durable queues (Cloud Tasks/Pub/Sub) are deferred until a concrete reliability or scheduling requirement appears.

## Cost-control principles

- scale Cloud Run to zero;
- bound maximum instances;
- enforce research-query/source limits;
- use provider quotas;
- centralize model costs in personal-ai-system;
- configure billing alerts during cloud deployment.

The API SQLAlchemy pool defaults to two connections and no overflow per instance. Cloud Run max instances and actual Neon connection limits must be selected together from account-specific values; overlapping revisions are included in the calculation.

## Infrastructure as code

Do not introduce a large Terraform hierarchy in the bootstrap. Add IaC after cloud deployment stabilizes and the resources to manage are clear.
