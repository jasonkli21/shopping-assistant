"""Shared freshness thresholds for research planning and decision views."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

DISPLAY_FRESHNESS = {
    "offer_max_age_hours": 24,
    "specification_max_age_days": 365,
    "claim_max_age_days": 90,
}

PLANNING_FRESHNESS = {
    "quick": {
        "offer_max_age_hours": 24,
        "specification_max_age_days": 365,
        "claim_max_age_days": 90,
    },
    "deep": {
        "offer_max_age_hours": 12,
        "specification_max_age_days": 180,
        "claim_max_age_days": 30,
    },
}


def offer_freshness(observed_at: datetime, *, now: datetime) -> str:
    return _freshness(observed_at, now, timedelta(hours=DISPLAY_FRESHNESS["offer_max_age_hours"]))


def evidence_freshness(
    category: str,
    *,
    published_at: datetime | None,
    retrieved_at: datetime,
    now: datetime,
    thresholds: dict[str, int] | None = None,
) -> str:
    limits = thresholds or DISPLAY_FRESHNESS
    if category in {"retailer_listing", "offer"}:
        return _freshness(retrieved_at, now, timedelta(hours=limits["offer_max_age_hours"]))
    if published_at is None:
        return "unknown"
    days = (
        limits["specification_max_age_days"]
        if category in {"manufacturer_specification", "manufacturer_claim"}
        else limits["claim_max_age_days"]
    )
    return _freshness(published_at, now, timedelta(days=days))


def _freshness(value: datetime, now: datetime, max_age: timedelta) -> str:
    value = _aware_utc(value)
    now = _aware_utc(now)
    return "stale" if now - value > max_age else "current"


def _aware_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
