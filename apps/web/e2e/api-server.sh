#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
api_root="$repository_root/apps/api"

if [[ -z "${E2E_DATABASE_URL:-}" ]]; then
  echo "E2E_DATABASE_URL must point to a disposable PostgreSQL database named *_e2e or *_e2e_test."
  exit 2
fi

cd "$api_root"
export SHOPPING_E2E_DATABASE_URL="$E2E_DATABASE_URL"
uv run python - <<'PY'
import os
import re
from sqlalchemy.engine import make_url
from shopping.config import get_settings

target = make_url(os.environ["SHOPPING_E2E_DATABASE_URL"])
database = (target.database or "").casefold()
if target.drivername != "postgresql+psycopg":
    raise SystemExit("E2E_DATABASE_URL must use postgresql+psycopg.")
if not re.search(r"(?:^|[_-])e2e(?:[_-]test)?$", database):
    raise SystemExit("Refusing to reset PostgreSQL: database name must end in _e2e or _e2e_test.")
if database in {"shopping", "production", "prod", "postgres"}:
    raise SystemExit("Refusing to reset a known application or system database.")

application = make_url(get_settings().database_url)
local_hosts = {"", "localhost", "127.0.0.1", "::1"}
target_host = (target.host or "").casefold().rstrip(".")
application_host = (application.host or "").casefold().rstrip(".")
same_host = target_host == application_host or (
    target_host in local_hosts and application_host in local_hosts
)
if (
    same_host
    and (target.port or 5432) == (application.port or 5432)
    and target.database == application.database
):
    raise SystemExit("Refusing to use the configured application database for E2E.")
PY

export DATABASE_URL="$E2E_DATABASE_URL"
export ENVIRONMENT=local
export AUTH_MODE=local
export PERSONAL_AI_MODE=fake
export SEARCH_PROVIDER=fake
export CORS_ORIGINS=http://127.0.0.1:5173

uv run python - <<'PY'
from sqlalchemy import create_engine, text
from shopping.config import get_settings

get_settings.cache_clear()
engine = create_engine(get_settings().database_url)
try:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
finally:
    engine.dispose()
PY

uv run alembic upgrade head
exec uv run uvicorn e2e_runtime:app --app-dir tests --host 127.0.0.1 --port 8000 --log-level info
