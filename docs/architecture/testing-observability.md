# Testing and Observability

## Testing strategy

### Unit tests

Use for deterministic domain behavior such as:

- requirement logic;
- product/variant matching helpers;
- offer normalization;
- evidence classification;
- comparison transformations.

### Fixture-based integration tests

Web research is nondeterministic, so extraction/retrieval behavior should be heavily tested against saved fixtures rather than live sites.

Future layout example:

```text
tests/fixtures/pages/
  vacuum-manufacturer.html
  vacuum-review.html
  chair-product.html
```

### Database integration tests

Use real PostgreSQL for repositories, transactions, migrations, and nontrivial queries.

### Provider contract tests

Keep a small number of live/recorded tests for provider adapters such as Tavily and personal-AI integration.

### End-to-end tests

Cover only major user journeys.

## AI evaluation fixtures

Maintain a growing evaluation corpus such as:

```text
tests/evals/
  chair-basic/
  vacuum-budget/
  monitor-comparison/
  luggage-alternative/
```

Evaluate structured intent, requirements, candidate quality, and known tricky cases.

## Observability

Persist research-run counters/metadata such as:

- query count;
- search result count;
- sources retrieved;
- products discovered;
- entity merges;
- claims extracted;
- extraction warnings;
- model/tool calls;
- failures/retries.

Development tooling should make prompts, tool inputs/outputs, structured AI results, entity-resolution decisions, and stored claims inspectable.
