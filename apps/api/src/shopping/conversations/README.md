# Conversations module

This module owns ordered, owner-scoped message history, database-fenced generation ownership, and explicit project-update proposal lifecycle. Model output stays a suggestion until `proposals.py` passes it to the Phase 1 project service for one atomic project-revision change.

`task.py` validates provider output against both the task schema and Phase 1 project and requirement rules, including values merged with the saved project context. Omitted and nullable values retain their Phase 1 meanings. Invalid output completes the assistant message as failed and does not create a proposal.

Accepting a message and assigning its worker ID, opaque lease token, expiry, and heartbeat timestamp happen in the same transaction. The supervisor heartbeats every 10 seconds against a 30-second lease. Completion, failure, and interruption lock the assistant row and require the current unexpired token; an expired or replaced worker cannot save a terminal result. Provider calls run after the input session closes.

Startup and periodic recovery claim only expired leases, then mark them interrupted. Recovery never retries provider work because a lost response may already have incurred a charge; a retry is an explicit new message command with a new request key. Graceful shutdown cancels owned work and persists interruption while its lease remains valid. A legacy generating row without lease metadata is given 180 seconds from creation before recovery, covering the previous 120-second maximum provider timeout during overlapping revisions. SSE attachment and request-key replay only read or return the saved command; neither starts generation.

Apply and dismiss lock the active owner-scoped project before locking a proposal. A foreign or tombstoned project returns 404 before replay or lifecycle details are disclosed. Successful apply records the committed revision, project snapshot, and UTC `applied_at`; replay returns that saved result while the project remains active.
