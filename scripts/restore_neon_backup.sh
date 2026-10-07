#!/usr/bin/env bash
set -euo pipefail
umask 077

required=(BACKUP_FILE BACKUP_AGE_IDENTITY_FILE PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSSLMODE)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required protected restore setting is missing: ${name}" >&2
    exit 2
  fi
done
if [[ "${RESTORE_DISPOSABLE_DATABASE_NAME:-}" != "$PGDATABASE" || -z "${RESTORE_DISPOSABLE_DATABASE_NAME:-}" || "${RESTORE_DISPOSABLE:-}" != "yes" ]]; then
  echo "Set RESTORE_DISPOSABLE=yes and RESTORE_DISPOSABLE_DATABASE_NAME to exactly PGDATABASE after creating a disposable empty database." >&2
  exit 2
fi
if [[ "$PGDATABASE" == shopping || "$PGDATABASE" == production || "$PGDATABASE" == prod || "$PGDATABASE" == postgres ]]; then
  echo "Refusing to restore into a known live/system database name." >&2
  exit 2
fi
if [[ "$PGSSLMODE" != require && "$PGSSLMODE" != verify-ca && "$PGSSLMODE" != verify-full ]]; then
  echo "PGSSLMODE must require TLS." >&2
  exit 2
fi
if [[ ! -f "$BACKUP_FILE" || ! -f "$BACKUP_AGE_IDENTITY_FILE" ]]; then
  echo "Backup or age identity file does not exist." >&2
  exit 2
fi
command -v age >/dev/null || { echo "age is required." >&2; exit 2; }
command -v pg_restore >/dev/null || { echo "pg_restore is required." >&2; exit 2; }

age --decrypt --identity "$BACKUP_AGE_IDENTITY_FILE" "$BACKUP_FILE" \
  | pg_restore --exit-on-error --no-owner --no-acl \
      --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname "$PGDATABASE"
