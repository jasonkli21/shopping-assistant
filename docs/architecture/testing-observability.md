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

Default tests use MockHTTP, task-aware AI fakes and keyed search fixtures; they do not make external calls. Tavily's credentialed compatibility smoke is explicitly selected with `pytest -m live --run-live`, a dedicated `TAVILY_LIVE_API_KEY` and an acknowledgment value. Its result is separate from offline tests and does not establish real discovery quality. See the [Tavily search contract](search-provider-contract.md).

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
- attempt count, status, sanitized error and provider request ID;
- provider-reported usage units where supplied;
- search result count;
- sources retrieved;
- products discovered;
- entity merges;
- claims extracted;
- extraction warnings;
- model/tool calls;
- failures/retries.

Development tooling should make prompts, tool inputs/outputs, structured AI results, entity-resolution decisions, and stored claims inspectable.
