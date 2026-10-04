# Research and Evidence Model

## Why evidence is first-class

The primary differentiator from ordinary shopping search is explainable synthesis across sources. The system must distinguish what a source actually says from what the app infers.

## Evidence ladder

Common source/evidence categories:

- manufacturer specification or claim;
- retailer listing;
- measured independent test;
- editorial/professional assessment;
- repeated community observation;
- individual anecdote;
- AI inference;
- explicit user judgment.

These are not interchangeable.

## Example

Manufacturer source:

> “Up to 60 minutes runtime.”

Store this as a qualified manufacturer claim, not simply as an unquestioned measured fact.

An independent review measuring 37 minutes under a specific mode may also be valid. Both can coexist because they have different contexts.

## Synthesis

A project assessment may conclude that battery life is sufficient for a particular user, but that assessment must remain distinct from the underlying claims.

## Source metadata

At minimum store:

- URL;
- title;
- publisher/domain;
- source type;
- retrieved timestamp;
- published timestamp where available;
- content hash where useful.

Prefer storing structured claims and small relevant excerpts/metadata rather than building an uncontrolled full-page web archive.

## Uncertainty

Product detail and comparison UX should expose uncertainty where evidence is incomplete, contradictory, stale, or anecdotal.
