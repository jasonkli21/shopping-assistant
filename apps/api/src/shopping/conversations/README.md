# Conversations module

This module owns ordered, owner-scoped message history, the local generation supervisor, and explicit project-update proposal lifecycle. Model output stays a suggestion until `proposals.py` passes it to the Phase 1 project service for one atomic project-revision change.

`task.py` validates provider output against both the task schema and Phase 1 project and requirement rules, including values merged with the saved project context. Omitted and nullable values retain their Phase 1 meanings. Invalid output completes the assistant message as failed and does not create a proposal.

The supervisor uses short-lived sessions on worker threads for synchronous database units. Provider calls run after the input session closes. Shutdown waits for an owned database unit to finish before handling cancellation and interruption, and lifespan startup marks work left generating by an earlier process as interrupted. Execution remains local and single-process.

Apply and dismiss lock the active owner-scoped project before locking a proposal. A foreign or tombstoned project returns 404 before replay or lifecycle details are disclosed. Successful apply records the committed revision, project snapshot, and UTC `applied_at`; replay returns that saved result while the project remains active.
