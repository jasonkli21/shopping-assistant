# Catalog module

Phase 4 owns canonical products, variants, project links, append-only retailer offers, source-page observations and resolution history. `commands.py` holds versioned normalization and reversible manual correction; `resolution.py` matches namespaced identifiers and exact observed variant dimensions; `reads.py` provides owner-scoped pages and details; `router.py` is the HTTP boundary. Page retrieval and extraction stay in `shopping.extraction`.

Candidates remain Phase 3 search observations even after a catalog link exists. A `ProjectProduct` points to one variant. Every offer points to the exact variant observed and carries its own amount/currency, availability, condition and timestamp. Refresh never moves an offer or overwrites a manual mapping. Extraction facts retain source excerpts and origin metadata; unknown fields stay absent.

Phase 5 may add source snapshots and claim evidence around these observation contracts. It must reuse the existing `PageRetriever` and keep catalog identifiers, source-backed claims and user corrections as distinct provenance.
