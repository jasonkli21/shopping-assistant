"""Operator workflow for complete owner export and purge beyond HTTP bounds."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shopping.accounts.export import export_owner_data, purge_owner_data
from shopping.config import Settings, validate_cloud_database_url


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a complete owner export or purge using the direct operator database URL."
    )
    parser.add_argument("--owner-id", required=True, type=UUID)
    parser.add_argument("--mode", choices=("export", "purge"), required=True)
    parser.add_argument("--output", type=Path, help="new file path required for export")
    parser.add_argument("--confirm", help="must be DELETE_MY_DATA for purge")
    args = parser.parse_args()

    settings = Settings(environment="local", auth_mode="local")
    database_url = settings.migration_database_url
    if not database_url:
        parser.error("MIGRATION_DATABASE_URL must be set to the verified direct database endpoint")
    try:
        validate_cloud_database_url(database_url)
    except ValueError as error:
        parser.error(str(error))

    if args.mode == "export" and args.output is None:
        parser.error("--output is required for a complete export")
    if args.mode == "purge" and args.confirm != "DELETE_MY_DATA":
        parser.error("purge requires --confirm DELETE_MY_DATA")
    if args.mode == "export" and args.confirm is not None:
        parser.error("--confirm is only supported for purge")

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as session:
            if args.mode == "export":
                payload = export_owner_data(
                    session, args.owner_id, record_limit=None, max_bytes=None
                )
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                print(json.dumps({"status": "exported", "path": str(output)}))
            else:
                counts = purge_owner_data(session, args.owner_id, record_limit=None)
                print(json.dumps({"status": "purged", "deleted_records": counts}, sort_keys=True))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
