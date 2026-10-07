from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from shopping.accounts.models import FirebaseOwnerBinding, OwnerPrivacyLifecycle  # noqa: F401
from shopping.catalog import models as catalog_models  # noqa: F401
from shopping.comparisons import models as comparison_models  # noqa: F401
from shopping.config import Settings, validate_cloud_database_url
from shopping.conversations import models as conversation_models  # noqa: F401
from shopping.db.base import Base
from shopping.evidence import models as evidence_models  # noqa: F401
from shopping.preferences import models as preference_models  # noqa: F401
from shopping.projects import models as project_models  # noqa: F401
from shopping.research import models as research_models  # noqa: F401


def _owner_record_counts(session: Session, owner_id) -> dict[str, int]:
    counts = {}
    for table in Base.metadata.sorted_tables:
        if "owner_id" not in table.c or table.name.startswith("owner_privacy_"):
            continue
        count = session.scalar(
            select(func.count()).select_from(table).where(table.c.owner_id == owner_id)
        )
        if count:
            counts[table.name] = count
    return counts


def main() -> int:
    # The operator command consumes the same identity values but deliberately
    # does not require the production-only API settings or initialize the app.
    settings = Settings(environment="local", auth_mode="local")
    parser = argparse.ArgumentParser(
        description=(
            "Bind the configured Firebase UID to the existing stable local owner. "
            "This command only applies changes when --apply is given."
        )
    )
    parser.add_argument("--firebase-uid", default=settings.firebase_owner_uid)
    parser.add_argument("--apply", action="store_true", help="write the binding after validation")
    args = parser.parse_args()

    if not settings.firebase_owner_uid or args.firebase_uid != settings.firebase_owner_uid:
        parser.error("--firebase-uid must exactly match the configured FIREBASE_OWNER_UID")
    if not settings.migration_database_url:
        parser.error("MIGRATION_DATABASE_URL must be set to the verified direct database endpoint")
    try:
        validate_cloud_database_url(settings.migration_database_url)
    except ValueError as error:
        parser.error(str(error))

    engine = create_engine(
        settings.migration_database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )
    try:
        with Session(engine) as session:
            existing_by_uid = session.get(FirebaseOwnerBinding, args.firebase_uid)
            existing_by_owner = session.scalar(
                select(FirebaseOwnerBinding).where(
                    FirebaseOwnerBinding.owner_id == settings.local_owner_id
                )
            )
            counts = _owner_record_counts(session, settings.local_owner_id)
            if existing_by_uid and existing_by_uid.owner_id != settings.local_owner_id:
                parser.error("The Firebase UID is already bound to a different owner UUID")
            if existing_by_owner and existing_by_owner.firebase_uid != args.firebase_uid:
                parser.error("The owner UUID is already bound to a different Firebase UID")

            report = {
                "firebase_uid_configured": True,
                "owner_id": str(settings.local_owner_id),
                "existing_binding": bool(existing_by_uid),
                "existing_private_record_counts": counts,
            }
            if existing_by_uid:
                report["result"] = "already_bound"
            elif args.apply:
                lifecycle = session.get(OwnerPrivacyLifecycle, settings.local_owner_id)
                if lifecycle is None:
                    session.add(
                        OwnerPrivacyLifecycle(owner_id=settings.local_owner_id, state="active")
                    )
                else:
                    lifecycle.state = "active"
                session.add(
                    FirebaseOwnerBinding(
                        firebase_uid=args.firebase_uid,
                        owner_id=settings.local_owner_id,
                    )
                )
                session.commit()
                report["result"] = "bound"
            else:
                report["result"] = "dry_run"
                report["apply_required"] = True
            print(json.dumps(report, sort_keys=True))
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
