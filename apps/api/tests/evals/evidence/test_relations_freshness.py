from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from shopping.evidence.assessment import _meets_requirement, _relation
from shopping.evidence.reads import freshness


def claim(text, value, **qualifiers):
    return SimpleNamespace(assertion_text=text, normalized_value=value, qualifiers=qualifiers)


def test_contextual_runtime_and_same_condition_conflict():
    marketing = claim("Up to 60 minutes in eco mode", 60, mode="eco", limit="up_to")
    measured = claim("37 minutes in normal mode", 37, mode="normal")
    assert _relation(marketing, measured)[0] == "different_context"
    peer = claim("31 minutes in normal mode", 31, mode="normal")
    assert _relation(measured, peer)[0] == "contradicts"
    different_unit = claim("1 hour in normal mode", 1, mode="normal", unit="h")
    assert _relation(measured, different_unit)[0] == "different_context"
    syndicated = claim("Up to 60 minutes in eco mode", 60, mode="eco", limit="up_to")
    assert _relation(marketing, syndicated)[0] == "duplicate"


def test_frozen_freshness_policy():
    now = datetime(2026, 10, 4, tzinfo=UTC)
    old_offer = now - timedelta(hours=25)
    old_review = now - timedelta(days=91)
    old_spec = now - timedelta(days=366)
    assert (
        freshness("retailer_listing", published_at=None, retrieved_at=old_offer, now=now) == "stale"
    )
    assert (
        freshness("independent_measurement", published_at=old_review, retrieved_at=now, now=now)
        == "stale"
    )
    assert (
        freshness("manufacturer_specification", published_at=old_spec, retrieved_at=now, now=now)
        == "stale"
    )
    assert (
        freshness("manufacturer_specification", published_at=None, retrieved_at=now, now=now)
        == "unknown"
    )
    assert freshness("retailer_listing", published_at=None, retrieved_at=now, now=now) == "current"


def test_promotional_upper_bound_does_not_prove_minimum_runtime():
    marketing = claim("Up to 60 minutes", 60, limit="up_to")
    requirement = {"operator": "gte", "value": 40, "unit": "min"}
    assert _meets_requirement(marketing, requirement) is None
    measured = claim("37 minutes", 37, mode="normal")
    assert _meets_requirement(measured, requirement) is False
