#!/usr/bin/env bash
set -euo pipefail
umask 077

required=(PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD PGSSLMODE BACKUP_DIR BACKUP_AGE_RECIPIENT)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Required protected backup setting is missing: ${name}" >&2
    exit 2
  fi
done
if [[ "$PGSSLMODE" != require && "$PGSSLMODE" != verify-ca && "$PGSSLMODE" != verify-full ]]; then
  echo "PGSSLMODE must require TLS." >&2
  exit 2
fi
retention_days="${BACKUP_RETENTION_DAYS:-30}"
if [[ ! "$retention_days" =~ ^[0-9]{1,4}$ ]]; then
  echo "BACKUP_RETENTION_DAYS must be an integer from 0 to 9999." >&2
  exit 2
fi
command -v pg_dump >/dev/null || { echo "pg_dump is required." >&2; exit 2; }
command -v age >/dev/null || { echo "age is required." >&2; exit 2; }

mkdir -p -- "$BACKUP_DIR"
chmod 700 -- "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
destination="$BACKUP_DIR/shopping-assistant-${stamp}.dump.age"
temporary="$destination.tmp"
trap 'rm -f -- "$temporary"' EXIT

pg_dump --format=custom --no-owner --no-acl \
  --host "$PGHOST" --port "$PGPORT" --username "$PGUSER" --dbname "$PGDATABASE" \
  | age --encrypt --recipient "$BACKUP_AGE_RECIPIENT" > "$temporary"
chmod 600 -- "$temporary"
mv -- "$temporary" "$destination"
find "$BACKUP_DIR" -type f -name 'shopping-assistant-*.dump.age' \
  -mtime "+$retention_days" -delete
printf 'Encrypted backup written: %s\n' "$destination"
