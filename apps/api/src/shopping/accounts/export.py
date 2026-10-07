from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import batched
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from shopping.accounts.models import OwnerPrivacyEvent
from shopping.catalog import models as catalog_models  # noqa: F401
from shopping.comparisons import models as comparison_models  # noqa: F401
from shopping.conversations import models as conversation_models  # noqa: F401
from shopping.db.base import Base
from shopping.evidence import models as evidence_models  # noqa: F401
from shopping.preferences import models as preference_models  # noqa: F401
from shopping.projects import models as project_models  # noqa: F401
from shopping.research import models as research_models  # noqa: F401

MAX_OWNER_RECORDS = 2_000
MAX_EXPORT_BYTES = 10 * 1024 * 1024
_NON_EXPORT_TABLES = {"firebase_owner_bindings", "owner_privacy_events"}
_OMITTED_EXPORT_COLUMNS = {"source_snapshots": {"relevant_text", "excerpts"}}
_URL_COLUMNS = {"url", "normalized_url", "requested_url", "final_url"}


class OwnerDataLimitExceeded(Exception):
    """Raised when owner data exceeds the bounds of one HTTP operation."""


def _primary_key(row: dict[str, Any], table) -> tuple[Any, ...]:
    return tuple(row[column.name] for column in table.primary_key.columns)


def _add_rows(collected: dict, table, rows, *, record_limit: int) -> int:
    target = collected.setdefault(table, {})
    total = sum(len(items) for items in collected.values())
    added = 0
    for row in rows:
        values = dict(row)
        key = _primary_key(values, table)
        if key not in target:
            target[key] = values
            added += 1
            total += 1
            if total > record_limit:
                raise OwnerDataLimitExceeded("Owner data exceeds the supported record limit.")
    return added


def _collect_owner_rows(session: Session, owner_id: UUID) -> dict:
    tables = [
        table for table in Base.metadata.sorted_tables if table.name not in {"owner_privacy_events"}
    ]
    collected: dict = {}
    for table in tables:
        if "owner_id" not in table.c:
            continue
        rows = session.execute(
            select(table)
            .where(table.c.owner_id == owner_id)
            .order_by(*table.primary_key.columns)
            .limit(MAX_OWNER_RECORDS + 1)
        ).mappings()
        _add_rows(collected, table, rows, record_limit=MAX_OWNER_RECORDS)

    changed = True
    while changed:
        changed = False
        for child in tables:
            for foreign_key in child.foreign_keys:
                parent = foreign_key.column.table
                parent_rows = collected.get(parent)
                if not parent_rows:
                    continue
                parent_values = {
                    row[foreign_key.column.name]
                    for row in parent_rows.values()
                    if row[foreign_key.column.name] is not None
                }
                if not parent_values:
                    continue
                child_column = child.c[foreign_key.parent.name]
                for value_batch in batched(sorted(parent_values, key=str), 1000):
                    rows = session.execute(
                        select(child)
                        .where(child_column.in_(value_batch))
                        .order_by(*child.primary_key.columns)
                    ).mappings()
                    changed |= bool(
                        _add_rows(collected, child, rows, record_limit=MAX_OWNER_RECORDS)
                    )
    return collected


def _safe_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        if parsed.username is None and parsed.password is None:
            return value
        host = parsed.hostname or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
        return urlunsplit(parsed._replace(netloc=host))
    except ValueError:
        return "[redacted-invalid-url]"


def _json_value(value: Any, field_name: str | None = None) -> Any:
    if field_name in {"authorization", "api_key", "password", "secret", "token"}:
        return "[redacted]"
    if field_name in _URL_COLUMNS and isinstance(value, str):
        value = _safe_url(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): _json_value(item, str(key).casefold()) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _export_value(column_name: str, value: Any) -> Any:
    return _json_value(value, column_name.casefold())


def export_owner_data(session: Session, owner_id: UUID) -> bytes:
    collected = _collect_owner_rows(session, owner_id)
    records: dict[str, list[dict[str, Any]]] = {}
    for table, rows in collected.items():
        if table.name in _NON_EXPORT_TABLES:
            continue
        omitted_columns = _OMITTED_EXPORT_COLUMNS.get(table.name, set())
        records[table.name] = [
            {
                column.name: _export_value(column.name, row[column.name])
                for column in table.columns
                if column.name not in omitted_columns
            }
            for row in sorted(rows.values(), key=lambda item: str(_primary_key(item, table)))
        ]

    payload = {
        "export_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "owner_id": str(owner_id),
        "records": records,
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_EXPORT_BYTES:
        raise OwnerDataLimitExceeded("Owner data exceeds the supported export size.")
    return encoded


def purge_owner_data(session: Session, owner_id: UUID) -> dict[str, int]:
    collected = _collect_owner_rows(session, owner_id)
    record_counts: dict[str, int] = {}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name == "owner_privacy_events":
            continue
        filters = []
        if "owner_id" in table.c:
            filters.append(table.c.owner_id == owner_id)
        for foreign_key in table.foreign_keys:
            parent_rows = collected.get(foreign_key.column.table)
            if not parent_rows:
                continue
            values = {
                row[foreign_key.column.name]
                for row in parent_rows.values()
                if row[foreign_key.column.name] is not None
            }
            if values:
                filters.append(table.c[foreign_key.parent.name].in_(values))
        if not filters:
            continue
        result = session.execute(delete(table).where(or_(*filters)))
        if result.rowcount:
            record_counts[table.name] = result.rowcount

    session.add(
        OwnerPrivacyEvent(owner_id=owner_id, event_type="purge", record_counts=record_counts)
    )
    session.commit()
    return record_counts
