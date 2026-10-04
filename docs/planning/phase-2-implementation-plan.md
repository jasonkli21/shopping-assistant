# Phase 2 — AI-assisted intent and conversation

Status: planned. Requires Phase 1's project service, revisions, owners and database harness. Read the [index](implementation-plans-index.md), Personal AI integration, AI/search design, UX assistant, API draft and ADR 0003.

## Outcome and scope

Within a durable project, “I need a lightweight vacuum under $400 that is good with hair” produces assistant text and an inspectable proposal for budget/requirements. The user applies it, then edits the resulting requirements manually. Invalid or interrupted model output never changes project state.

Smallest slice: existing project → message → fake streamed assistant response → validated proposal → preview/apply → persisted editable requirements. Home may first create a Phase 1 project from raw intent then send the initial message; creation is still useful if AI fails. Scope includes conversation history, proposal lifecycle, SSE, task-shaped fakes and a verified HTTP adapter when an actual Personal AI contract is available. No search, discovery, catalog, arbitrary tool agent, direct model SDK or memory promotion.

## Contracts

Modules: `conversations/`, `projects/service.py`, `integrations/personal_ai/`, web `features/assistant/`, transport/types and tests/evals. Add `conversations` (one default thread per project initially), `messages` (role, ordinal, text, generating/completed/failed/interrupted state, request_key/hash, paired message ID, provider metadata, timestamps) and `project_update_proposals` (message/project IDs, base revision, versioned validated JSONB operations, pending/applied/dismissed/stale status, applied revision/time). Keep text and structured proposal state distinct. Owner follows project; enforce scoped references and unique conversation ordinals/request keys.

Shopping task `interpret_shopping_intent.v1` accepts a bounded project snapshot, requirements, limited recent messages and the new user message. Output schema: `assistant_message`, `clarification_questions` (bounded strings), `project_updates` (whitelisted goal/category/budget fields), and `requirement_operations` (`add|update|remove`, stable IDs for existing items, validated Phase 1 fields). Unknown operation/field or foreign IDs fails schema validation. The model cannot set owner, revisions, status/deletion, execute external tools, retrieve arbitrary URLs or promote memory. Preserve user wording/origin and avoid duplicate requirement adds on proposal replay.

`PersonalAIClient.generate` remains supported. Extend the client with a provider-neutral `stream` only to support verified capabilities: typed text deltas and a final structured envelope (not arbitrary vendor events). If Personal AI only supports generation, the development adapter can emit pending then a final response; do not pretend buffered text is live tokens. Map verified wire schema inside the adapter; record endpoint, auth, timeout, structured-output and stream/error contract. Never invent endpoints in the separate service. The Phase 0 echo fake must become fixture/task-aware for this task.

API:

- `GET /projects/{id}/conversations` and `GET /projects/{id}/messages` return ordered paginated durable history/proposals.
- `POST /projects/{id}/messages` accepts text (1–8000), request_key and expected_version, persists user/assistant placeholders atomically, returns 202 with message/conversation IDs. Replay returns same IDs; mismatched replay 409. At most one active response per conversation; competing new commands 409.
- `GET /projects/{id}/messages/stream?message_id=...` attaches to that response, never starts a second generation. SSE types `snapshot|delta|proposal|complete|error`, JSON data with message ID and sequence, heartbeats, bounded buffering. Complete is emitted only after final text/proposal persistence. Error codes are sanitized. Reconnect receives persisted snapshot and subsequent deltas; full token replay is not promised. Already-terminal messages return snapshot plus terminal event. A GET history path remains authoritative.
- `POST /projects/{id}/proposals/{proposal_id}/apply` with expected_version applies all operations through Phase 1 service in one transaction; applied replay returns prior outcome. Stale base revision returns 409 and marks stale; user requests a fresh proposal after reconciling. Add dismiss command. Token deltas never mutate domain state.

Use a supervised in-process task owned by application lifespan for generation. It owns no request session, has timeout and bounded concurrency, persists failures and is explicitly single-process local execution. A stream disconnect detaches the subscriber; bounded generation may finish and be inspected later. On local process restart mark unfinished generation interrupted; do not claim distributed safety. No generic research executor is necessary for conversation. Before Phase 9 multi-instance operation, Phase 7/9 must revisit active execution and interruption ownership.

## Work packages and order

### 2A — Contract verification, schemas and fixtures

Inspect the actual Personal AI API docs/OpenAPI or supplied contract. Write a contract note of capabilities verified and missing. Implement request/final validation, stream event types and task fixtures for valid intent, clarification-only, no-op, malformed JSON, invalid budget, foreign requirement IDs, timeout and refusal. Prompt treats user/history as data; final proposals explicitly distinguish inferred preferences and hard constraints. Stub any unavailable wire capability behind the same adapter and visibly record live checks as not run.

### 2B — Durable conversation and safe proposals

Migrate tables with indexes/unique constraints. Persist user/placeholder and command key together without incrementing project-context revision; model I/O outside transactions. Persist final text and validated proposal atomically; invalid output marks response failed without partial project writes. Record task/schema/prompt version and provider request ID where available, excluding credentials and unnecessary raw sensitive payloads. Apply/dismiss lifecycle tests cover stale project edits during generation, duplicate apply, deleted project and concurrent messages.

### 2C — Streaming transport and lifecycle

Add supervisor and attach-only SSE. Test split UTF-8/SSE chunks in frontend parser, multiline event framing, heartbeat ignore, truncated final envelope, disconnect, repeated subscription, terminal reconnect and restart interruption. Limit message/context/output sizes, stream duration and per-project active calls. No global mutable task dictionary as the durable source of truth. Refuse malformed provider events safely.

### 2D — Assistant UX and evaluation

Desktop collapsible panel/mobile drawer with history, send pending, streamed text, retry/new-message affordance and failure state. Display proposal diff, source “AI suggestion,” apply/dismiss, and conflict explanation without losing typed text. Closing the panel must not erase history or apply suggestions. Retry failed generation uses a new command key explicitly; resubmission due to lost acknowledgment retains the old one.

Create `tests/evals/intent/` for vacuum budget/hair, chair desk dimensions, monitor alternatives, contradictory requirements, unspecified currency, ambiguous “lightweight,” and irrelevant/malicious instructions. Offline structural acceptance: no invented currency/hard requirement where unclear, clarification when needed, all mutations validated, 0 unauthorized operations across fixtures. Fixture tests establish safety, not live semantic quality; optional live eval records actual outputs and human judgments separately.

## Acceptance, checks and handoff

The vacuum slice is durable, visible and editable; proposal confirmation is explicit. All invalid/truncated/refused/timeout responses leave the original project unchanged. A stale proposal cannot overwrite newer edits. Command replay/stream reconnect cannot duplicate a user message, generation or application. History remains available after reload. UI loading/errors/mobile and proposal controls are tested.

Run `make validate`, Phase 1 PostgreSQL tests plus conversation/proposal tests, OpenAPI/type generation check, and focused offline intent evals (add documented command such as `uv run pytest tests/evals/intent`). Live adapter test is opt-in via `uv run pytest -m live --run-live`, with dedicated configuration, never default CI; record real Personal AI compatibility as pending if unavailable. Manually test disconnect/reload and narrow viewport with fake streaming.

Suggested commits: contract/task fixtures; persistence/proposals; adapter/SSE lifecycle; assistant UX/evals; completion evidence. Review: Can arbitrary model output mutate state? Are apply semantics atomic and revision-safe? Does “streaming” reflect verified capability? Are prompt versions and failures inspectable without exposing secrets? Is a canceled browser distinct from a canceled generation?

Handoff: bounded task API and streaming envelope, safe proposals/application service, message context builder, fixture-aware AI client, contract note and interruption limits. Phase 3 can reuse generation for query planning. Phase 6 extends proposal operations explicitly, not via a generic unrestricted mutation language. Unresolved external gap: actual Personal AI streaming/auth/structured-output support; offline development can proceed, but live compatibility is not satisfied by a fake.
