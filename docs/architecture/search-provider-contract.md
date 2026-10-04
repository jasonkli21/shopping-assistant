# Search provider contract

## Neutral shopping boundary

`SearchProvider.search(SearchQuery)` returns a bounded `SearchResponse` containing neutral `title`, `url`, and optional `snippet` observations, an optional provider request ID, and optional integer `usage_units`. Research owns validation, safe URL handling, truncation, lineage, and persistence. Shopping code does not consume Tavily ranking scores or raw response fields. The Tavily adapter requests only short snippets; it never asks for answers, raw page content, or images.

Search attempts persist an integer usage count when the adapter can report one. It is provider-reported usage metadata, not a currency amount or a claim about the user's bill. Missing usage remains unknown. Search cost/quotas can change with account configuration; the live smoke records the reported value for that call.

## Tavily wire contract verified 2026-10-04

Implementation follows the current [official Tavily Search API reference](https://docs.tavily.com/documentation/api-reference/endpoint/search): HTTPS `POST https://api.tavily.com/search`, `Authorization: Bearer <server-side key>`, `Content-Type: application/json`, and a JSON `query`. The adapter sends `search_depth: basic`, `topic: general`, `max_results` capped to the smaller of the query budget and Tavily's documented maximum of 20, `include_answer: false`, `include_raw_content: false`, `include_images: false`, and `include_usage: true`.

Each response must have a `results` array (at most 20 entries) with string `title` and `url`; `content`, when present, must be a string and becomes the neutral snippet. Optional `request_id` is stored as provider request ID. Optional `usage.credits` becomes `usage_units` only when it is a bounded nonnegative integer. Unknown vendor fields such as scores, raw content, answer, images, or publication metadata are discarded. Response bodies are limited to 2 MB and HTTP redirects are disabled.

The adapter applies a 12-second HTTP timeout by default; the run supervisor adds a shorter remaining-run deadline when needed. It maps 401 to `provider_auth`, 429 to `rate_limited`, 432/433 to `quota_exceeded`, documented 400/422 and 403 rejections to `provider_rejected`, 5xx and transport errors to `provider_unavailable`, and timeout to `provider_timeout`. Invalid or oversized response payloads become `malformed_response`. Provider response bodies and headers are never copied into stored errors. Tavily's documented status examples and fields can change; re-verify this contract before changing the adapter.

Provider selection defaults to the deterministic fake. Selecting Tavily requires `SEARCH_PROVIDER=tavily` and `TAVILY_API_KEY`; an absent key fails startup clearly. A configured live failure stays a failure and never falls back to fake data. Normal test collection uses `MockTransport` and no external network.

## Live smoke

The opt-in test is `apps/api/tests/search/test_live_tavily.py`. It makes one query and records result titles, result count, request ID, and reported usage metadata. It does not persist candidates or prove full-app discovery quality. To run it explicitly, use a dedicated key and acknowledge that the provider may charge for the request:

```bash
cd apps/api
TAVILY_LIVE_API_KEY=... TAVILY_LIVE_ACK=I_ACCEPT_TAVILY_BILLABLE_CALL \
  uv run pytest -m live --run-live tests/search/test_live_tavily.py -v
```

Do not use a production key for routine tests. This repository has no configured Tavily credential, so live compatibility and query quality remain unverified until a human runs the guarded smoke. The separate Personal AI service still has no verified structured `plan_discovery.v1` route; local automatic planning uses its task-aware fake, while users can provide explicit search queries without Personal AI.
