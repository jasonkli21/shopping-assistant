# AI and Search Architecture

## Principle

Do not make a single LLM call that “searches the web and recommends products” as an opaque operation. Use explicit, persisted stages.

## Research flow

```text
User intent
   ↓
Project context / requirements
   ↓
Research planner
   ↓
Search queries
   ↓
Candidate discovery
   ↓
Source retrieval
   ↓
Structured extraction
   ↓
Product entity resolution
   ↓
Claims and evidence
   ↓
Project-relative assessment
   ↓
User-facing synthesis
```

## Discovery vs deep research

### Candidate discovery

Broad and cheap. Gather enough to identify plausible product candidates:

- name/model;
- brand;
- rough price;
- source URL;
- snippet/category clues.

### Deep product research

Selective and more expensive. Retrieve promising candidates from sources such as:

- manufacturer pages;
- independent/professional reviews;
- measured testing;
- retailers;
- community discussions.

Do not deeply research every search result.

## Search provider abstraction

All web search goes through `SearchProvider`. The initial live provider is Tavily, with a fake deterministic provider for tests. Brave can be added later as a second adapter.

Shopping logic must not depend on Tavily-specific response types.

Phase 3 persists bounded run, query, attempt and result records plus provisional candidates. A candidate is a URL-grouped search observation within one run; it is not a normalized product or a verified source. Duplicate observations retain every result/query reference. See the [implemented Tavily wire and error contract](search-provider-contract.md), which records the live contract check date and the still-unverified credentialed smoke.

## Retrieval

`PageRetriever` retrieves source content. Extraction is a separate responsibility.

Start with ordinary HTTP retrieval. Add browser automation only as a fallback for pages that materially require rendering.

## Structured AI output

Persistent mutations must use validated structured output. Do not parse assistant prose to infer domain updates.

Example separation:

```json
{
  "assistant_message": "...",
  "project_updates": {
    "budget": {"target": 400, "maximum": 500}
  },
  "requirements": []
}
```

## Model access

Shopping-domain functions use `PersonalAIClient` rather than direct OpenAI/Anthropic/etc. SDKs. Shopping owns its task schemas and prompts; the personal-AI system owns provider/model access.

## Research budgets

Research should always be bounded by configuration such as:

- maximum search queries;
- maximum discovered candidates;
- maximum deep-research products;
- maximum sources per product;
- maximum retrieved pages.

These limits improve both cost control and system predictability.
