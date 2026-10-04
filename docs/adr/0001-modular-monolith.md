# ADR 0001: Modular Monolith

## Status

Accepted.

## Decision

Build the Shopping Assistant as a modular monolith rather than microservices.

## Rationale

The application benefits from strong domain boundaries but does not have operational scale that justifies distributed service complexity. Research execution can later be delegated to job infrastructure through an adapter without splitting the whole backend.
