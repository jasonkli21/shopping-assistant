# UX Design

## Core interaction model

The UI combines:

1. **Conversation** for expressing intent, asking questions, and directing research.
2. **Structured workspace** for durable state: requirements, products, evidence, comparisons, shortlist, and notes.

Chat should never be the only place important state exists.

## Top-level navigation

```text
Home
Shopping Projects
  └── Project
       ├── Overview
       ├── Discover
       ├── Compare
       ├── Shortlist
       └── Research
Saved Products
Shopping Profile
Settings
```

`Saved Products` and `Shopping Profile` can start lightweight.

## Home

Primary action:

> “What are you looking for?”

Submitting natural-language intent creates a shopping project rather than an ephemeral search.

Below the entry point, show recent projects and project status.

## Project workspace

Desktop concept:

```text
┌──────────────┬───────────────────────────┬────────────────────┐
│ Project nav  │ Current structured view   │ AI assistant       │
│              │                           │                    │
│ Overview     │                           │ project-aware chat │
│ Discover     │                           │                    │
│ Compare      │                           │                    │
│ Shortlist    │                           │                    │
│ Research     │                           │                    │
└──────────────┴───────────────────────────┴────────────────────┘
```

The assistant panel may collapse. On mobile it becomes a sheet/drawer.

## Overview

Show:

- project goal;
- budget;
- must-haves;
- soft preferences;
- project status;
- candidate/researched/shortlisted counts;
- current shortlist.

Every requirement should be directly editable.

## Discover

Discovery should combine:

- category understanding (“what matters for this purchase?”);
- candidate products;
- project-specific filters;
- fit explanations;
- research state.

Do not imitate a generic e-commerce catalog. The experience should communicate research and decision support.

## Product cards

Prioritize project fit:

- image;
- canonical product name;
- approximate/current offers;
- short fit explanation;
- requirement matches/conflicts;
- shortlist and reject actions.

Avoid an opaque universal numeric score.

## Product detail

Sections:

- product identity and variant;
- known offers;
- project fit;
- key structured facts;
- research summary;
- recurring pros/cons;
- uncertainty;
- source list;
- evidence inspection;
- alternatives;
- project notes.

Users should be able to inspect evidence behind material assertions.

## Compare

Comparison dimensions are category- and project-specific.

The user should be able to ask:

- “Only show meaningful differences.”
- “Add warranty.”
- “Compare durability evidence.”
- “Ignore aesthetics.”

Comparisons should persist as project state.

## Shortlist

Shortlist is the application’s cart-equivalent but represents a decision set, not checkout intent.

Store:

- why saved;
- concerns;
- user notes;
- relevant offers;
- comparison context.

## Rejection

Provide explicit reasons such as:

- too expensive;
- missing feature;
- too large;
- dislike appearance;
- weak reviews;
- wrong category;
- already owned;
- other.

Rejections immediately influence the project. Persistent profile learning is a separate step.

## Shopping Profile

The profile shows pending candidates separately from accepted preferences. A user can propose a saved project preference or explicitly select a rejected-product judgment, then review and accept the candidate before it becomes reusable. Scope and source stay visible; project requirements already applied from the profile remain editable and independent of later profile changes. Projects must opt in before new suggestions appear, and must-haves and constraints keep priority over soft preferences. External Personal AI memory is labeled unavailable until a user-scoped contract is verified.

## Mobile

Use focused screens/tabs for `Overview`, `Discover`, `Compare`, and `Shortlist`, plus a floating assistant action. Do not force a desktop three-pane layout onto mobile.
