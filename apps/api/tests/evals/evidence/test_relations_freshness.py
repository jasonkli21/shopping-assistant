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
    measured = claim("37 minutes", 37, mode="normal", unit="min")
    assert _meets_requirement(measured, requirement) is False
    assert _meets_requirement(claim("37 minutes", 37, mode="normal"), requirement) is None


def test_bound_does_not_establish_an_exact_value_even_at_the_endpoint():
    assert (
        _meets_requirement(
            claim("Up to 60 minutes", 60, unit="min", limit="up_to"),
            {"operator": "eq", "value": 60, "unit": "min"},
        )
        is None
    )
    assert (
        _meets_requirement(
            claim("At least 45 minutes", 45, unit="min", limit="at_least"),
            {"operator": "eq", "value": 45, "unit": "min"},
        )
        is None
    )


def test_stated_at_least_bound_supports_only_compatible_lower_bound():
    stated = claim("At least 45 minutes", 45, unit="min", limit="at_least")
    assert _meets_requirement(stated, {"operator": "gte", "value": 40, "unit": "min"}) is True
    assert _meets_requirement(stated, {"operator": "lte", "value": 50, "unit": "min"}) is None
