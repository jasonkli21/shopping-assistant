# Personal AI contract check for Shopping Assistant Phase 2

Checked on 2026-10-03 against the separate repository's `docs/api-contract.md`
and `backend/src/personal_ai/api/routes.py`.

The upstream public route inventory includes owner-scoped conversations and a
chat message SSE route under `/v1/conversations/{conversation_id}/messages`.
Its streamed payload is ordinary chat text and terminal message status. The
checked contract does not define a generic shopping-task generation endpoint,
typed request envelope for shopping schemas, JSON-schema-constrained output,
provider request ID contract, or a typed task-specific refusal envelope. The
existing chat route therefore does not establish that it can safely implement
`interpret_shopping_intent.v1`.

This repository does not call that chat route or invent an endpoint. The
`PersonalAIClient` protocol remains the integration boundary. Local default
development uses a deterministic task-aware fake. Setting
`PERSONAL_AI_MODE=external` selects an adapter that reports
`provider_unavailable` until the upstream task contract is supplied and
verified. `PERSONAL_AI_URL` is not used to guess a route. No live provider
compatibility result is claimed for Phase 2.

The fake returns one final structured envelope after generation. It does not
represent buffered text as provider token streaming. The local SSE endpoint
persists the final response and supports attachment/reconnection independently
of provider streaming support.

## Phase 8 memory capability check — 2026-10-05

The upstream `docs/api-contract.md` and `backend/src/personal_ai/api/routes.py`
were checked again for Phase 8. The public
`GET /v1/conversations/{conversation_id}/context` route accepts up to 20
explicit memory IDs only for gated, read-only planning inspection. Its result
contains planning metadata and omits memory text and vectors; it is not a
retrieval contract for a shopping request. The normal chat path can retrieve
memories and schedule memory extraction after completion, which does not provide
the separate, user-approved compact preference proposal and retraction
operations this app requires.

The checked public API has no memory list/create/edit/delete/propose/retract
routes or idempotency contract for those operations. `/tasks/memory` is a
private authenticated worker route for Pub/Sub job processing, not a user
memory API. No Personal AI memory adapter or external write has been added.
Shopping preferences remain local, owner-scoped and usable without that
integration. Recheck the upstream contract before adding an adapter.
