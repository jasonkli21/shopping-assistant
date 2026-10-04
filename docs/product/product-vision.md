# Product Vision

## Purpose

The Shopping Assistant is a personal research and decision-support tool for buying physical products. It focuses on the difficult part of shopping—understanding needs, discovering candidates, researching evidence, comparing tradeoffs, and deciding what to shortlist—rather than checkout.

## Core job

> Help the user go from “I need something” to “I understand my options and know what I should seriously consider buying.”

Examples:

- “I need a chair for my apartment.”
- “Find me a cordless vacuum under $400.”
- “What is like this product, but cheaper?”
- “Compare these three monitors.”
- “Teach me what matters when buying an air purifier.”

## Primary artifact: Shopping Project

Each shopping need becomes a durable `ShoppingProject` containing:

- intent and goal;
- editable requirements and budget;
- research runs and sources;
- candidate products;
- product-relative assessments;
- comparisons;
- shortlist and rejections;
- user notes;
- conversation history.

A shopping project is more important than a single search query or chat transcript.

## Product principles

### Start from intent, not keywords

Natural-language needs should become explicit, editable requirements. AI inference must not silently become durable truth.

### Explain tradeoffs rather than output rankings

Prefer evidence-backed differences and fit explanations over opaque universal scores.

### Separate facts from judgment

Keep manufacturer specifications, measured observations, reviewer claims, AI assessments, and user judgments distinct.

### Preserve evidence and provenance

Important claims should be traceable to sources and evidence types.

### Make search iterative

Follow-up questions should refine an existing project rather than reset the search.

### Shortlist, not cart

The app stops before checkout. `Shortlist` is the primary decision state.

### Learn carefully

Project-specific preferences should not automatically become long-term personal preferences. Persistent preference promotion should be explicit or strongly inspectable.

## In scope for MVP

- create shopping projects;
- define and edit requirements;
- conversational intent interpretation;
- web product discovery;
- product/variant/offer normalization;
- multi-source research and evidence;
- product detail pages;
- shortlist and rejection;
- side-by-side/difference-focused comparison;
- continuing project-aware conversation;
- outbound links to sellers/manufacturers.

## Explicitly out of scope initially

- checkout and payments;
- order placement;
- shipping logistics;
- returns processing;
- marketplace/seller accounts;
- loyalty systems;
- coupon optimization;
- automated purchasing;
- multi-user collaboration.

## Long-term direction

Possible extensions include price tracking, browser/share-sheet capture, email purchase recognition, visual discovery, product ownership history, new-model detection, and cross-application context from travel or finance. These are roadmap items, not bootstrap requirements.
