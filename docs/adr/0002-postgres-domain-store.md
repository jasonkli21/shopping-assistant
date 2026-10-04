# ADR 0002: PostgreSQL as Shopping Domain Store

## Status

Accepted.

## Decision

Use PostgreSQL locally and in production-compatible deployments for authoritative shopping-domain state.

## Rationale

Product/variant/offer, research/evidence, project/product, comparison, and shortlist relationships are naturally relational. JSONB provides flexibility for category-specific product attributes.
