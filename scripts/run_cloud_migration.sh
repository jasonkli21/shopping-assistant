#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${MIGRATION_DATABASE_URL:-}" ]]; then
  echo "Set MIGRATION_DATABASE_URL to the verified direct Neon endpoint." >&2
  exit 2
fi
if [[ "${BACKUP_RESTORE_POINT_CONFIRMED:-}" != "yes" ]]; then
  echo "Confirm a usable Neon backup/restore point before migration by setting BACKUP_RESTORE_POINT_CONFIRMED=yes." >&2
  exit 2
fi

cd "$(dirname "$0")/../apps/api"
export DATABASE_URL="$MIGRATION_DATABASE_URL"
uv run --locked alembic upgrade head
uv run --locked alembic check
uv run --locked alembic current
