# Data Model

PostgreSQL is the authoritative shopping-domain datastore; category-specific flexibility is handled with relational structure plus JSONB where appropriate.

## Core relationships

```text
User
 ├── ShoppingProfile
 │    └── Preference
 │
 └── ShoppingProject
      ├── Requirement
      ├── ResearchRun
      │    ├── SearchQuery
      │    │    ├── SearchAttempt
      │    │    └── SearchResult
      │    ├── DiscoveryCandidate
      │    │    └── CandidateSearchResult
      │    └── RetrievedSource
      ├── ProjectProduct
      │    ├── Assessment
      │    ├── UserNote
      │    └── Decision
      ├── Comparison
      └── Conversation

Product
 └── ProductVariant
      ├── ProductAttribute
      └── RetailOffer

Source
 └── Claim
      └── Evidence
```

## Product identity

Model identity as:

```text
Product family
   ↓
Product variant
   ↓
Retail offer
```

The same product may appear at many URLs and retailers. A URL is not a product identity.

Entity resolution must allow manual correction.

## Price

Price belongs to a retailer-specific `RetailOffer`, not directly to the canonical product.

Typical offer fields:

- retailer;
- URL;
- observed price;
- currency;
- availability;
- condition;
- observed timestamp.

## Category-specific attributes

Use a hybrid relational + JSONB model.

Relational/common fields:

- brand;
- category;
- canonical name;
- model identifiers;
- variant identity.

Category-specific details can initially live in JSONB, for example chair seat dimensions or vacuum battery configuration. Promote attributes to first-class normalized dimensions only when repeated query/filter behavior justifies it.

## Project-relative product state

Never store “great fit” on the canonical product. Use `ProjectProduct` to represent fit in a particular project.

Typical fields:

- project/product reference;
- discovery reason;
- fit status;
- shortlist/rejection status;
- project-specific summary;
- user notes.

## Research run

Research must be persisted as a first-class entity for debuggability and refresh.

Typical fields:

- project;
- type/objective;
- status;
- start/completion timestamps;
- input context;
- model/tool configuration references;
- summary;
- error state.

Associated records include search queries, retrieved sources, extracted claims, and candidate products.

## Sources, claims, evidence, assessments

Do not collapse these concepts.

- **Source**: where information came from.
- **Claim**: an assertion extracted from a source.
- **Evidence**: supporting context/measurement/provenance for a claim.
- **Assessment**: shopping-app interpretation of evidence, often project-relative.
- **User judgment**: explicit user preference or decision.

## Freshness

Store retrieval/observation timestamps. Different data changes at different rates:

- dimensions/specifications: usually stable;
- offers/availability: volatile;
- ownership/reliability consensus: evolves over time.

The model should support future freshness policies without treating entire products as uniformly stale/fresh.

## Initial table set

Expected over the implementation phases:

- `shopping_projects`
- `project_requirements`
- `products`
- `product_variants`
- `product_attributes`
- `project_products`
- `retail_offers`
- `research_runs`
- `search_queries`
- `search_attempts`
- `search_results`
- `discovery_candidates`
- `candidate_search_results`
- `sources`
- `claims`
- `claim_evidence`
- `product_assessments`
- `comparisons`
- `shortlist_entries`
- `product_rejections`
- `shopping_preferences`
- `conversations`
- `messages`

Do not create every table in Phase 0. Add schema as each phase requires it.

## Execution-plan refinements

The table list above is conceptual, not a requirement to create every listed table. Detailed [phase plans](../planning/implementation-plans-index.md) use provisional discovery candidates in Phase 3, canonical catalog/variant/project-product mapping in Phase 4, and immutable source snapshots plus claims/evidence in Phase 5. Category attributes start as provenance-bearing JSONB, without redundant EAV storage. Phase 6 may use one current decision row plus history instead of separate contradictory shortlist/rejection tables; API shortlist/rejection resources remain. Owner scoping begins with projects, precise variant references drive decisions, and offers always retain observation time/currency.
