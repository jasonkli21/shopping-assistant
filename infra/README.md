# Infrastructure

Infrastructure is intentionally minimal during early local development.

Planned production target:

- Frontend: Firebase Hosting
- API: Google Cloud Run
- Database: Neon PostgreSQL
- Secrets: Google Secret Manager
- Authentication: Firebase Authentication
- Long-running research, if needed: Cloud Run Jobs

Do not introduce Terraform or queue infrastructure until deployment stabilizes and a concrete need exists.
