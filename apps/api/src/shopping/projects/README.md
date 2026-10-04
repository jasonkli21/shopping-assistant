# Projects module

This module owns project/requirement schemas, owner-scoped persistence, and revision-checked context edits. Its Phase 1 validators define the field, currency, money, JSON-value, criterion, and requirement-count boundaries shared by manual writes and AI proposals.

`apply_ai_proposal` runs inside the locked project transaction. It validates the final requirement count, applies removals before additions so a replacement fits at the 100-item limit, and advances the project revision once for the full proposal. The conversations module remains responsible for validating model output and requiring the user's explicit apply action.
