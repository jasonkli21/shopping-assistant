/**
 * Generated from the FastAPI OpenAPI contract.
 * Regenerate with `make api-types`; do not edit by hand.
 */

export interface components {
  schemas: {
    ApiError: {
      "code": string;
      "message": string;
      "details"?: unknown;
      "request_id"?: null | string;
    };
    ApiErrorEnvelope: {
      "error": components["schemas"]["ApiError"];
    };
    AssessmentRead: {
      "id": string;
      "research_run_id": string;
      "project_product_id": string;
      "project_revision": number;
      "product_revision": number;
      "variant_revision": number;
      "generated_at": string;
      "context_stale": boolean;
      "summary": string;
      "conclusions": Array<Record<string, unknown>>;
      "uncertainties": Array<string>;
    };
    CancelResult: {
      "run": components["schemas"]["ResearchRunRead"];
      "replayed": boolean;
    };
    CandidateAction: {
      "expected_profile_version": number;
    };
    CandidateCreate: {
      "expected_project_version": number;
      "expected_profile_version": number;
      "source_requirement_id"?: null | string;
      "source_project_product_id"?: null | string;
      "label": string;
      "key": string;
      "operator"?: "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value": unknown;
      "unit"?: string;
      "monetary"?: boolean;
      "category_scopes": Array<string>;
      "rationale"?: string;
    };
    CandidateMutation: {
      "candidate": components["schemas"]["PreferenceCandidateRead"];
      "preference"?: components["schemas"]["PreferenceRead"] | null;
      "replayed"?: boolean;
    };
    CandidateNormalizationState: {
      "candidate_id": string;
      "project_product_id": null | string;
      "product_id": null | string;
      "variant_id": null | string;
      "status": "auto_linked" | "manual_linked" | "unresolved" | "reverted" | null;
      "latest_observation_status": "succeeded" | "failed" | "blocked" | "unsupported" | null;
      "latest_failure_code": null | string;
      "catalog_version": number;
      "project_version": number;
      "reason"?: null | string;
      "warnings"?: Array<string>;
      "observed_at"?: null | string;
      "can_revert_correction"?: boolean;
    };
    CandidatePage: {
      "items": Array<components["schemas"]["CandidateRead"]>;
      "next_cursor"?: null | string;
    };
    CandidateRead: {
      "id": string;
      "project_id": string;
      "research_run_id": string;
      "provisional_name": string;
      "brand_clue"?: null | string;
      "model_clue"?: null | string;
      "category_clue"?: null | string;
      "discovery_reason": string;
      "indicative_price_text"?: null | string;
      "observed_at": string;
      "search_results": Array<components["schemas"]["CandidateResultRead"]>;
      "normalization"?: components["schemas"]["CandidateNormalizationState"] | null;
    };
    CandidateResultRead: {
      "search_result_id": string;
      "query_id": string;
      "query_text": string;
      "purpose": string;
      "title": string;
      "url": string;
      "snippet": null | string;
      "result_rank": number;
      "received_at": string;
    };
    CatalogCorrectionCommand: {
      "request_key": string;
      "expected_catalog_version": number;
      "expected_project_version": number;
      "reason": string;
      "target_variant_id"?: null | string;
      "new_variant"?: components["schemas"]["NewVariantCorrection"] | null;
      "new_product"?: components["schemas"]["NewProductCorrection"] | null;
    };
    CatalogCorrectionRead: {
      "candidate_id": string;
      "event_id": string;
      "status": "manual_linked" | "reverted";
      "previous_project_product_id": null | string;
      "selected_project_product_id": null | string;
      "catalog_version": number;
      "project_version": number;
      "reason": string;
      "replayed"?: boolean;
    };
    CatalogCorrectionRevertCommand: {
      "request_key": string;
      "expected_catalog_version": number;
      "expected_project_version": number;
    };
    CatalogNormalizationRead: {
      "candidate_id": string;
      "observation_id": string;
      "event_id": string;
      "status": "auto_linked" | "unresolved" | "failed" | "blocked" | "unsupported";
      "project_product_id": null | string;
      "product_id": null | string;
      "variant_id": null | string;
      "catalog_version": number;
      "project_version": number;
      "reason": string;
      "failure_code"?: null | string;
      "warnings"?: Array<string>;
      "observed_at": string;
      "replayed"?: boolean;
    };
    CatalogVariantChoice: {
      "variant_id": string;
      "product_id": string;
      "canonical_name": string;
      "brand": null | string;
      "category": null | string;
      "model_family": null | string;
      "variant_name": string;
      "identity_attributes": Record<string, unknown>;
    };
    CatalogVariantChoicePage: {
      "items": Array<components["schemas"]["CatalogVariantChoice"]>;
      "next_cursor": null | string;
      "catalog_version": number;
    };
    CategoryAttributeCorrection: {
      "key": string;
      "value": boolean | number | string;
      "unit"?: null | string;
    };
    ClaimDetailRead: {
      "id": string;
      "attribute_key": string;
      "assertion_text": string;
      "evidence_category": string;
      "qualifiers": Record<string, unknown>;
      "source_id": string;
      "snapshot_id": string;
      "source_title": null | string;
      "source_url": string;
      "published_at": null | string;
      "retrieved_at": string;
      "freshness": "current" | "stale" | "unknown";
      "normalized_value"?: unknown;
      "evidence_excerpt": string;
      "locator": Record<string, unknown>;
      "content_hash": string;
      "validation_warnings": Array<Record<string, unknown>>;
      "relations": Array<components["schemas"]["ClaimRelationRead"]>;
    };
    ClaimRelationRead: {
      "related_claim_id": string;
      "relation": string;
      "basis": string;
      "origin": string;
    };
    ClaimSummaryRead: {
      "id": string;
      "attribute_key": string;
      "assertion_text": string;
      "evidence_category": string;
      "qualifiers": Record<string, unknown>;
      "source_id": string;
      "snapshot_id": string;
      "source_title": null | string;
      "source_url": string;
      "published_at": null | string;
      "retrieved_at": string;
      "freshness": "current" | "stale" | "unknown";
    };
    ComparisonCell: {
      "project_product_id": string;
      "status": "known" | "unknown" | "conflict" | "stale" | "incomparable";
      "value"?: unknown;
      "unit"?: null | string;
      "comparison_value"?: unknown;
      "provenance"?: Record<string, unknown>;
    };
    ComparisonCreate: {
      "expected_version": number;
      "title"?: string;
      "project_product_ids": Array<string>;
      "dimensions": Array<components["schemas"]["ComparisonDimensionInput"]>;
      "display_mode"?: "all" | "differences";
    };
    ComparisonDimensionInput: {
      "key": string;
      "label": string;
      "unit"?: null | string;
      "dimension_type": "fact" | "offer" | "evidence" | "project_fit" | "user_note";
    };
    ComparisonDimensionRead: {
      "key": string;
      "label": string;
      "unit": null | string;
      "dimension_type": "fact" | "offer" | "evidence" | "project_fit" | "user_note";
      "cells": Array<components["schemas"]["ComparisonCell"]>;
      "equal"?: boolean;
    };
    ComparisonPage: {
      "items": Array<components["schemas"]["ComparisonRead"]>;
      "next_cursor"?: null | string;
    };
    ComparisonPatch: {
      "expected_version": number;
      "expected_comparison_version": number;
      "title"?: null | string;
      "project_product_ids"?: Array<string> | null;
      "dimensions"?: Array<components["schemas"]["ComparisonDimensionInput"]> | null;
      "display_mode"?: "all" | "differences" | null;
    };
    ComparisonProductRead: {
      "project_product_id": string;
      "product_id": string;
      "variant_id": string;
      "canonical_name": string;
      "brand": null | string;
      "category": null | string;
      "variant_name": string;
      "identity_attributes": Record<string, unknown>;
      "product_revision": number;
      "variant_revision": number;
    };
    ComparisonRead: {
      "id": string;
      "project_id": string;
      "title": string;
      "display_mode": "all" | "differences";
      "comparison_revision": number;
      "project_revision": number;
      "snapshot_id": string;
      "generated_at": string;
      "stale": boolean;
      "products": Array<components["schemas"]["ComparisonProductRead"]>;
      "dimensions": Array<components["schemas"]["ComparisonDimensionRead"]>;
      "definition_dimensions": Array<components["schemas"]["ComparisonDimensionRead"]>;
      "hidden_equal_dimensions"?: number;
    };
    ComparisonRegenerate: {
      "expected_version": number;
      "expected_comparison_version": number;
    };
    ConversationPage: {
      "items": Array<components["schemas"]["ConversationRead"]>;
      "next_cursor"?: null | string;
    };
    ConversationRead: {
      "id": string;
      "project_id": string;
      "created_at": string;
      "updated_at": string;
    };
    DecisionCommand: {
      "expected_version": number;
      "request_key": string;
      "reason"?: string;
      "rejection_reason"?: "too_expensive" | "missing_feature" | "too_large" | "appearance" | "weak_evidence" | "wrong_category" | "already_owned" | "other" | null;
      "concerns"?: Array<string>;
      "selected_offer_id"?: null | string;
    };
    DecisionEventRead: {
      "id": string;
      "project_product_id": string;
      "command_type": string;
      "from_state": "considering" | "shortlisted" | "rejected" | "purchased";
      "to_state": "considering" | "shortlisted" | "rejected" | "purchased";
      "actor": "owner" | "assistant";
      "reason": string;
      "rejection_reason": "too_expensive" | "missing_feature" | "too_large" | "appearance" | "weak_evidence" | "wrong_category" | "already_owned" | "other" | null;
      "concerns"?: Array<string>;
      "selected_offer_id"?: null | string;
      "project_version": number;
      "created_at": string;
      "replayed"?: boolean;
    };
    DecisionMutationResult: {
      "event": components["schemas"]["DecisionEventRead"];
      "replayed": boolean;
    };
    DecisionPage: {
      "items": Array<components["schemas"]["ProjectProductDecisionRead"]>;
      "project_version": number;
      "next_cursor"?: null | string;
    };
    DecisionRead: {
      "project_product_id": string;
      "state": "considering" | "shortlisted" | "rejected" | "purchased";
      "reason": string;
      "rejection_reason": "too_expensive" | "missing_feature" | "too_large" | "appearance" | "weak_evidence" | "wrong_category" | "already_owned" | "other" | null;
      "concerns": Array<string>;
      "selected_offer_id": null | string;
      "version": number;
      "updated_at": null | string;
      "events"?: Array<components["schemas"]["DecisionEventRead"]>;
    };
    FavoriteCommand: {
      "expected_version": number;
    };
    FavoriteRead: {
      "variant_id": string;
      "favorite": boolean;
      "version": number;
      "updated_at"?: null | string;
    };
    MessageCreate: {
      "text": string;
      "request_key": string;
      "expected_version": number;
      "selected_project_product_ids"?: Array<string>;
      "comparison_id"?: null | string;
    };
    MessageCreated: {
      "user_message_id": string;
      "assistant_message_id": string;
      "conversation_id": string;
      "replayed": boolean;
    };
    MessagePage: {
      "items": Array<components["schemas"]["MessageRead"]>;
      "next_cursor"?: null | string;
    };
    MessageRead: {
      "id": string;
      "conversation_id": string;
      "project_id": string;
      "paired_message_id": null | string;
      "ordinal": number;
      "role": "user" | "assistant";
      "text": string;
      "status": "generating" | "completed" | "failed" | "interrupted";
      "request_key"?: null | string;
      "snapshot_revision": null | number;
      "sequence": number;
      "error_code": null | string;
      "clarification_questions"?: Array<string>;
      "citation_ids"?: Array<string>;
      "created_at": string;
      "completed_at": null | string;
      "proposal"?: components["schemas"]["ProposalRead"] | null;
    };
    NewProductCorrection: {
      "canonical_name": string;
      "brand"?: null | string;
      "category"?: null | string;
      "model_family"?: null | string;
      "variant_name"?: string;
      "identity_attributes"?: Record<string, boolean | number | string>;
      "category_attributes"?: Array<components["schemas"]["CategoryAttributeCorrection"]>;
    };
    NewVariantCorrection: {
      "product_id": string;
      "display_name": string;
      "identity_attributes"?: Record<string, boolean | number | string>;
      "category_attributes"?: Array<components["schemas"]["CategoryAttributeCorrection"]>;
    };
    NormalizeCandidateCommand: {
      "request_key": string;
      "expected_catalog_version": number;
      "expected_project_version": number;
    };
    NoteMutationResult: {
      "note": components["schemas"]["NoteRead"];
      "project_version": number;
    };
    NoteRead: {
      "id": string;
      "project_id": string;
      "project_product_id": null | string;
      "text": string;
      "version": number;
      "created_at": string;
      "updated_at": string;
    };
    NoteWrite: {
      "expected_version": number;
      "text": string;
    };
    OfferPage: {
      "items": Array<components["schemas"]["OfferRead"]>;
      "next_cursor": null | string;
      "catalog_version": number;
    };
    OfferRead: {
      "id": string;
      "variant_id": string;
      "observation_id": null | string;
      "research_source_attempt_id"?: null | string;
      "retailer_name": string;
      "retailer_domain": null | string;
      "url": string;
      "amount": null | string;
      "currency": null | string;
      "availability": "in_stock" | "out_of_stock" | "preorder" | "unknown";
      "condition": "new" | "used" | "refurbished" | "unknown";
      "observed_at": string;
      "freshness": "current" | "stale";
    };
    PreferenceCandidateRead: {
      "id": string;
      "source_kind": "requirement" | "decision";
      "source_project_id": null | string;
      "source_requirement_id": null | string;
      "source_project_product_id": null | string;
      "source_decision_id": null | string;
      "source_project_revision": number;
      "source_project_title": null | string;
      "source_available": boolean;
      "source_stale": boolean;
      "label": string;
      "key": string;
      "operator": "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value": unknown;
      "unit": string;
      "monetary": boolean;
      "category_scopes": Array<string>;
      "rationale": string;
      "status": "pending" | "accepted" | "dismissed" | "stale";
      "created_at": string;
      "resolved_at": null | string;
    };
    PreferencePatch: {
      "expected_profile_version": number;
      "expected_preference_revision": number;
      "label"?: null | string;
      "key"?: null | string;
      "operator"?: "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value"?: unknown;
      "unit"?: null | string;
      "monetary"?: boolean | null;
      "category_scopes"?: Array<string> | null;
      "status"?: "active" | "revoked" | null;
    };
    PreferenceRead: {
      "id": string;
      "source_kind": "requirement" | "decision";
      "source_candidate_id": null | string;
      "source_project_id": null | string;
      "source_requirement_id": null | string;
      "source_project_product_id": null | string;
      "source_decision_id": null | string;
      "source_project_title": null | string;
      "source_available": boolean;
      "key": string;
      "operator": "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value": unknown;
      "unit": string;
      "monetary": boolean;
      "category_scopes": Array<string>;
      "label": string;
      "strength": string;
      "status": "active" | "revoked";
      "revision": number;
      "accepted_at": string;
      "updated_at": string;
    };
    PreferenceSuggestionsRead: {
      "reuse_enabled": boolean;
      "profile_reuse_enabled": boolean;
      "profile_revision": number;
      "items": Array<components["schemas"]["PreferenceRead"]>;
    };
    ProductIdentifierRead: {
      "id": string;
      "scheme": "manufacturer_model" | "gtin" | "mpn" | "retailer_sku";
      "namespace": string;
      "value": string;
      "observation_id": null | string;
    };
    ProductRead: {
      "id": string;
      "canonical_name": string;
      "brand": null | string;
      "category": null | string;
      "model_family": null | string;
      "revision": number;
      "created_at": string;
      "updated_at": string;
      "variants": Array<components["schemas"]["ProductVariantRead"]>;
    };
    ProductSourcesRead: {
      "product_id": string;
      "variant_id": null | string;
      "sources": Array<components["schemas"]["SourceAttemptRead"]>;
    };
    ProductVariantRead: {
      "id": string;
      "product_id": string;
      "display_name": string;
      "identity_attributes": Record<string, unknown>;
      "category_attributes": Record<string, unknown>;
      "revision": number;
      "identifiers": Array<components["schemas"]["ProductIdentifierRead"]>;
      "offers": Array<components["schemas"]["OfferRead"]>;
    };
    ProfilePatch: {
      "expected_version": number;
      "reuse_enabled": boolean;
    };
    ProfileRead: {
      "id": string;
      "revision": number;
      "reuse_enabled": boolean;
      "preferences": Array<components["schemas"]["PreferenceRead"]>;
      "candidates": Array<components["schemas"]["PreferenceCandidateRead"]>;
      "updated_at": string;
    };
    ProjectCreate: {
      "title": string;
      "goal": string;
      "category"?: null | string;
      "budget_target"?: null | string;
      "budget_maximum"?: null | string;
      "budget_currency"?: null | string;
      "notes"?: null | string;
      "requirements"?: Array<components["schemas"]["RequirementCreate"]>;
    };
    ProjectPage: {
      "items": Array<components["schemas"]["ProjectSummary"]>;
      "next_cursor": null | string;
    };
    ProjectPatch: {
      "expected_version": number;
      "title"?: null | string;
      "goal"?: null | string;
      "category"?: null | string;
      "status"?: "active" | "completed" | "archived" | null;
      "budget_target"?: null | string;
      "budget_maximum"?: null | string;
      "budget_currency"?: null | string;
      "notes"?: null | string;
      "reuse_preferences"?: boolean | null;
    };
    ProjectProductDecisionRead: {
      "product": components["schemas"]["ProjectProductRead"];
      "decision": components["schemas"]["DecisionRead"];
    };
    ProjectProductPage: {
      "items": Array<components["schemas"]["ProjectProductRead"]>;
      "next_cursor": null | string;
      "catalog_version": number;
      "project_version": number;
    };
    ProjectProductRead: {
      "id": string;
      "project_id": string;
      "product_id": string;
      "variant_id": string;
      "canonical_name": string;
      "brand": null | string;
      "category": null | string;
      "model_family": null | string;
      "variant_name": string;
      "identity_attributes": Record<string, unknown>;
      "category_attributes": Record<string, unknown>;
      "first_candidate_id": null | string;
      "discovery_reason": string;
      "created_at": string;
      "offers": Array<components["schemas"]["OfferRead"]>;
    };
    ProjectProductResearchRead: {
      "project_product_id": string;
      "latest_run_id": null | string;
      "latest_run_status": null | string;
      "assessments": Array<components["schemas"]["AssessmentRead"]>;
      "has_more_assessments": boolean;
      "claims": Array<components["schemas"]["ClaimSummaryRead"]>;
      "has_more_claims": boolean;
      "sources": Array<components["schemas"]["SourceAttemptRead"]>;
      "has_more_sources": boolean;
      "state": "no_research" | "no_evidence" | "blocked" | "partial" | "researched";
    };
    ProjectRead: {
      "id": string;
      "title": string;
      "goal": string;
      "category": null | string;
      "status": "active" | "completed" | "archived";
      "budget_target": null | string;
      "budget_maximum": null | string;
      "budget_currency": null | string;
      "notes": null | string;
      "reuse_preferences": boolean;
      "revision": number;
      "created_at": string;
      "updated_at": string;
      "requirements": Array<components["schemas"]["RequirementRead"]>;
    };
    ProjectSummary: {
      "id": string;
      "title": string;
      "goal": string;
      "category": null | string;
      "status": "active" | "completed" | "archived";
      "budget_target": null | string;
      "budget_maximum": null | string;
      "budget_currency": null | string;
      "notes": null | string;
      "reuse_preferences": boolean;
      "revision": number;
      "created_at": string;
      "updated_at": string;
    };
    ProposalCommand: {
      "expected_version": number;
    };
    ProposalMutationResult: {
      "proposal": components["schemas"]["ProposalRead"];
      "project": components["schemas"]["ProjectRead"] | null;
      "replayed": boolean;
    };
    ProposalRead: {
      "id": string;
      "project_id": string;
      "assistant_message_id": string;
      "base_revision": number;
      "schema_version": number;
      "operations": Record<string, unknown>;
      "status": "pending" | "applied" | "dismissed" | "stale";
      "applied_revision": null | number;
      "applied_at": null | string;
      "applied_project"?: components["schemas"]["ProjectRead"] | null;
      "created_at": string;
      "updated_at": string;
    };
    RequirementCreate: {
      "kind": "must_have" | "preference" | "constraint";
      "label": string;
      "detail"?: null | string;
      "attribute_key"?: null | string;
      "operator"?: "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value"?: unknown;
      "unit"?: null | string;
    };
    RequirementPatch: {
      "expected_version": number;
      "kind"?: "must_have" | "preference" | "constraint" | null;
      "label"?: null | string;
      "detail"?: null | string;
      "attribute_key"?: null | string;
      "operator"?: "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value"?: unknown;
      "unit"?: null | string;
      "position"?: null | number;
    };
    RequirementRead: {
      "id": string;
      "project_id": string;
      "kind": "must_have" | "preference" | "constraint";
      "label": string;
      "detail": null | string;
      "attribute_key": null | string;
      "operator": "eq" | "gte" | "lte" | "contains" | "one_of" | null;
      "value": unknown;
      "unit": null | string;
      "position": number;
      "origin": "user" | "ai_confirmed";
      "source_preference_id"?: null | string;
      "source_preference_revision"?: null | number;
      "source_preference_scope"?: Array<string> | null;
      "created_at": string;
      "updated_at": string;
    };
    ResearchBudgets: {
      "max_queries"?: null | number;
      "max_candidates"?: null | number;
      "max_results"?: null | number;
      "max_results_per_query"?: null | number;
      "max_attempts"?: null | number;
      "max_products"?: null | number;
      "max_sources_per_product"?: null | number;
      "max_pages"?: null | number;
      "max_total_bytes"?: null | number;
      "max_ai_calls"?: null | number;
      "max_output_chars"?: null | number;
      "deadline_seconds"?: null | number;
      "max_concurrent"?: null | number;
    };
    ResearchCreate: {
      "objective": string;
      "type"?: "discovery" | "product_research";
      "mode"?: "quick" | "deep";
      "request_key": string;
      "expected_version": number;
      "budgets"?: components["schemas"]["ResearchBudgets"];
      "source_targets"?: components["schemas"]["ResearchSourceTargets"] | null;
      "refresh_of_run_id"?: null | string;
      "refresh_targets"?: Array<"offers" | "claims"> | null;
      "manual_queries"?: Array<string> | null;
      "selected_project_product_ids"?: Array<string> | null;
    };
    ResearchCreated: {
      "run_id": string;
      "status": string;
      "replayed": boolean;
    };
    ResearchJobAttemptRead: {
      "number": number;
      "status": "running" | "succeeded" | "failed" | "canceled" | "uncertain";
      "error_code": null | string;
      "provider_request_id": null | string;
      "budget_consumed": Record<string, number>;
      "started_at": string;
      "finished_at": null | string;
    };
    ResearchJobRead: {
      "id": string;
      "stage_type": "plan" | "search" | "retrieve" | "extract" | "assess" | "refresh_offer";
      "status": "queued" | "running" | "succeeded" | "failed" | "canceled";
      "attempt_count": number;
      "max_attempts": number;
      "not_before": string;
      "heartbeat_at": null | string;
      "error_code": null | string;
      "attempts"?: Array<components["schemas"]["ResearchJobAttemptRead"]>;
    };
    ResearchRetry: {
      "request_key": string;
      "expected_version": number;
    };
    ResearchRunPage: {
      "items": Array<components["schemas"]["ResearchRunRead"]>;
      "next_cursor"?: null | string;
    };
    ResearchRunRead: {
      "id": string;
      "project_id": string;
      "objective": string;
      "type": "discovery" | "product_research";
      "mode"?: "quick" | "deep";
      "refresh_of_run_id"?: null | string;
      "status": "queued" | "running" | "succeeded" | "partial" | "failed" | "canceled" | "interrupted";
      "snapshot_revision": number;
      "effective_budgets": Record<string, number>;
      "queries_planned": number;
      "queries_completed": number;
      "queries_failed": number;
      "attempts_used": number;
      "results_found": number;
      "candidates_found": number;
      "skipped_count": number;
      "summary"?: null | string;
      "error_code"?: null | string;
      "queued_at": string;
      "started_at"?: null | string;
      "finished_at"?: null | string;
      "replayed"?: boolean;
      "queries"?: Array<components["schemas"]["SearchQueryRead"]>;
      "targets"?: Array<components["schemas"]["ResearchTargetProgressRead"]>;
      "stages"?: Array<components["schemas"]["ResearchStageProgressRead"]>;
      "jobs"?: Array<components["schemas"]["ResearchJobRead"]>;
    };
    ResearchSourceTargets: {
      "source_classes"?: Array<"manufacturer_specification" | "independent_measurement" | "editorial_assessment" | "retailer_listing" | "community_observation"> | null;
      "include_domains"?: Array<string>;
      "exclude_domains"?: Array<string>;
    };
    ResearchStageProgressRead: {
      "stage": "planning" | "extraction" | "relations" | "assessment";
      "target_project_product_id": null | string;
      "source_snapshot_id": null | string;
      "attempt_number": number;
      "status": "running" | "succeeded" | "failed" | "skipped" | "canceled";
      "error_code": null | string;
      "validation_warnings": Array<Record<string, unknown>>;
    };
    ResearchTargetProgressRead: {
      "project_product_id": string;
      "product_id": string;
      "variant_id": string;
      "status": "queued" | "running" | "succeeded" | "partial" | "failed" | "skipped";
      "sources_attempted": number;
      "sources_retrieved": number;
      "claims_created": number;
      "error_code"?: null | string;
    };
    SavedProductPage: {
      "items": Array<components["schemas"]["SavedProductRead"]>;
      "next_cursor"?: null | string;
    };
    SavedProductRead: {
      "variant_id": string;
      "favorite": boolean;
      "version": number;
      "updated_at"?: null | string;
      "product_id": string;
      "canonical_name": string;
      "brand": null | string;
      "category": null | string;
      "variant_name": string;
      "identity_attributes": Record<string, unknown>;
      "offers": Array<components["schemas"]["OfferRead"]>;
    };
    SearchAttemptRead: {
      "id": string;
      "attempt_number": number;
      "provider": string;
      "status": "running" | "succeeded" | "failed" | "canceled" | "uncertain";
      "error_code"?: null | string;
      "provider_request_id"?: null | string;
      "results_count": number;
      "usage_units"?: null | number;
      "started_at": string;
      "finished_at"?: null | string;
    };
    SearchQueryRead: {
      "id": string;
      "target_project_product_id"?: null | string;
      "ordinal": number;
      "text": string;
      "purpose": string;
      "max_results": number;
      "state": "queued" | "running" | "succeeded" | "failed" | "skipped" | "canceled";
      "retry_not_before"?: null | string;
      "results_count": number;
      "candidates_count": number;
      "error_code"?: null | string;
      "created_at": string;
      "started_at"?: null | string;
      "completed_at"?: null | string;
      "attempts": Array<components["schemas"]["SearchAttemptRead"]>;
    };
    SourceAttemptRead: {
      "id": string;
      "snapshot_id": null | string;
      "source_id": string;
      "requested_url": string;
      "final_url": string;
      "title": null | string;
      "publisher": null | string;
      "classification": string;
      "classification_basis": null | string;
      "status": string;
      "reason": null | string;
      "retrieved_at": string;
      "published_at": null | string;
      "freshness": "current" | "stale" | "unknown";
      "bytes_read": null | number;
      "offer_status"?: "succeeded" | "no_offer" | "identity_mismatch" | "unsupported" | "failed" | null;
      "offer_error_code"?: null | string;
      "offer_observation"?: Record<string, unknown>;
    };
    SourceSnapshotRead: {
      "id": string;
      "source_id": string;
      "title": null | string;
      "final_url": string;
      "classification": string;
      "content_hash": string;
      "published_at": null | string;
      "retrieved_at": string;
      "excerpt": string;
      "claims": Array<components["schemas"]["ClaimSummaryRead"]>;
    };
  };
}

export interface paths {
  "/health": {
    "get": operations["health_health_get"];
  };
  "/products": {
    "get": operations["list_catalog_variants_products_get"];
  };
  "/products/{product_id}": {
    "get": operations["get_product_products__product_id__get"];
  };
  "/products/{product_id}/offers": {
    "get": operations["list_product_offers_products__product_id__offers_get"];
  };
  "/products/{product_id}/sources": {
    "get": operations["product_sources_products__product_id__sources_get"];
  };
  "/profile": {
    "get": operations["get_profile_profile_get"];
    "patch": operations["patch_profile_profile_patch"];
  };
  "/profile/preference-candidates/{candidate_id}/accept": {
    "post": operations["accept_candidate_profile_preference_candidates__candidate_id__accept_post"];
  };
  "/profile/preference-candidates/{candidate_id}/dismiss": {
    "post": operations["dismiss_candidate_profile_preference_candidates__candidate_id__dismiss_post"];
  };
  "/profile/preferences/{preference_id}": {
    "delete": operations["revoke_preference_profile_preferences__preference_id__delete"];
    "patch": operations["patch_preference_profile_preferences__preference_id__patch"];
  };
  "/projects": {
    "get": operations["list_projects_projects_get"];
    "post": operations["create_project_projects_post"];
  };
  "/projects/{project_id}": {
    "delete": operations["delete_project_projects__project_id__delete"];
    "get": operations["get_project_projects__project_id__get"];
    "patch": operations["patch_project_projects__project_id__patch"];
  };
  "/projects/{project_id}/candidates": {
    "get": operations["list_candidates_projects__project_id__candidates_get"];
  };
  "/projects/{project_id}/candidates/{candidate_id}/correction": {
    "post": operations["correct_candidate_projects__project_id__candidates__candidate_id__correction_post"];
  };
  "/projects/{project_id}/candidates/{candidate_id}/correction/revert": {
    "post": operations["revert_candidate_correction_projects__project_id__candidates__candidate_id__correction_revert_post"];
  };
  "/projects/{project_id}/candidates/{candidate_id}/normalize": {
    "post": operations["normalize_candidate_projects__project_id__candidates__candidate_id__normalize_post"];
  };
  "/projects/{project_id}/claims/{claim_id}": {
    "get": operations["claim_detail_projects__project_id__claims__claim_id__get"];
  };
  "/projects/{project_id}/comparisons": {
    "get": operations["list_comparisons_projects__project_id__comparisons_get"];
    "post": operations["create_comparison_projects__project_id__comparisons_post"];
  };
  "/projects/{project_id}/comparisons/{comparison_id}": {
    "delete": operations["delete_comparison_projects__project_id__comparisons__comparison_id__delete"];
    "get": operations["get_comparison_projects__project_id__comparisons__comparison_id__get"];
    "patch": operations["patch_comparison_projects__project_id__comparisons__comparison_id__patch"];
  };
  "/projects/{project_id}/comparisons/{comparison_id}/regenerate": {
    "post": operations["regenerate_comparison_projects__project_id__comparisons__comparison_id__regenerate_post"];
  };
  "/projects/{project_id}/conversations": {
    "get": operations["list_conversations_projects__project_id__conversations_get"];
  };
  "/projects/{project_id}/messages": {
    "get": operations["list_messages_projects__project_id__messages_get"];
    "post": operations["create_message_projects__project_id__messages_post"];
  };
  "/projects/{project_id}/messages/stream": {
    "get": operations["attach_message_stream_projects__project_id__messages_stream_get"];
  };
  "/projects/{project_id}/notes": {
    "delete": operations["delete_project_note_projects__project_id__notes_delete"];
    "get": operations["get_project_note_projects__project_id__notes_get"];
    "put": operations["put_project_note_projects__project_id__notes_put"];
  };
  "/projects/{project_id}/preference-candidates": {
    "post": operations["create_candidate_projects__project_id__preference_candidates_post"];
  };
  "/projects/{project_id}/preference-suggestions": {
    "get": operations["preference_suggestions_projects__project_id__preference_suggestions_get"];
  };
  "/projects/{project_id}/preferences/{preference_id}/apply": {
    "post": operations["apply_preference_projects__project_id__preferences__preference_id__apply_post"];
  };
  "/projects/{project_id}/products": {
    "get": operations["list_project_products_projects__project_id__products_get"];
  };
  "/projects/{project_id}/products/{project_product_id}/decision": {
    "get": operations["get_decision_projects__project_id__products__project_product_id__decision_get"];
  };
  "/projects/{project_id}/products/{project_product_id}/notes": {
    "delete": operations["delete_product_note_projects__project_id__products__project_product_id__notes_delete"];
    "get": operations["get_product_note_projects__project_id__products__project_product_id__notes_get"];
    "put": operations["put_product_note_projects__project_id__products__project_product_id__notes_put"];
  };
  "/projects/{project_id}/products/{project_product_id}/purchased": {
    "delete": operations["undo_product_purchased_projects__project_id__products__project_product_id__purchased_delete"];
    "post": operations["mark_product_purchased_projects__project_id__products__project_product_id__purchased_post"];
  };
  "/projects/{project_id}/products/{project_product_id}/research": {
    "get": operations["product_research_projects__project_id__products__project_product_id__research_get"];
  };
  "/projects/{project_id}/proposals/{proposal_id}/apply": {
    "post": operations["apply_proposal_projects__project_id__proposals__proposal_id__apply_post"];
  };
  "/projects/{project_id}/proposals/{proposal_id}/dismiss": {
    "post": operations["dismiss_proposal_projects__project_id__proposals__proposal_id__dismiss_post"];
  };
  "/projects/{project_id}/rejections": {
    "get": operations["list_rejections_projects__project_id__rejections_get"];
  };
  "/projects/{project_id}/rejections/{project_product_id}": {
    "delete": operations["undo_rejection_projects__project_id__rejections__project_product_id__delete"];
    "post": operations["reject_product_projects__project_id__rejections__project_product_id__post"];
  };
  "/projects/{project_id}/requirements": {
    "get": operations["list_requirements_projects__project_id__requirements_get"];
    "post": operations["create_requirement_projects__project_id__requirements_post"];
  };
  "/projects/{project_id}/requirements/{requirement_id}": {
    "delete": operations["delete_requirement_projects__project_id__requirements__requirement_id__delete"];
    "patch": operations["patch_requirement_projects__project_id__requirements__requirement_id__patch"];
  };
  "/projects/{project_id}/research": {
    "get": operations["list_research_projects__project_id__research_get"];
    "post": operations["create_research_projects__project_id__research_post"];
  };
  "/projects/{project_id}/research/{research_run_id}": {
    "get": operations["get_research_projects__project_id__research__research_run_id__get"];
  };
  "/projects/{project_id}/research/{research_run_id}/cancel": {
    "post": operations["cancel_research_projects__project_id__research__research_run_id__cancel_post"];
  };
  "/projects/{project_id}/research/{research_run_id}/retry": {
    "post": operations["retry_research_projects__project_id__research__research_run_id__retry_post"];
  };
  "/projects/{project_id}/shortlist": {
    "get": operations["list_shortlist_projects__project_id__shortlist_get"];
  };
  "/projects/{project_id}/shortlist/{project_product_id}": {
    "delete": operations["undo_shortlist_projects__project_id__shortlist__project_product_id__delete"];
    "post": operations["shortlist_product_projects__project_id__shortlist__project_product_id__post"];
  };
  "/projects/{project_id}/sources/{snapshot_id}": {
    "get": operations["source_snapshot_projects__project_id__sources__snapshot_id__get"];
  };
  "/saved-products": {
    "get": operations["list_saved_products_saved_products_get"];
  };
  "/saved-products/{variant_id}": {
    "get": operations["get_saved_product_saved_products__variant_id__get"];
  };
  "/saved-products/{variant_id}/favorite": {
    "delete": operations["unfavorite_product_saved_products__variant_id__favorite_delete"];
    "put": operations["favorite_product_saved_products__variant_id__favorite_put"];
  };
}

export interface operations {
  "accept_candidate_profile_preference_candidates__candidate_id__accept_post": {
    parameters: {
      path: {
        "candidate_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["CandidateAction"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CandidateMutation"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "apply_preference_projects__project_id__preferences__preference_id__apply_post": {
    parameters: {
      path: {
        "preference_id": string;
        "project_id": string;
      };
      query: {
        "expected_preference_revision": number;
        "expected_profile_version": number;
        "expected_project_version": number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "apply_proposal_projects__project_id__proposals__proposal_id__apply_post": {
    parameters: {
      path: {
        "project_id": string;
        "proposal_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ProposalCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProposalMutationResult"];
      } };
      "404": { content?: {
        "application/json"?: undefined;
      } };
      "409": { content?: {
        "application/json"?: undefined;
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "attach_message_stream_projects__project_id__messages_stream_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "message_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": unknown;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "cancel_research_projects__project_id__research__research_run_id__cancel_post": {
    parameters: {
      path: {
        "project_id": string;
        "research_run_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CancelResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "claim_detail_projects__project_id__claims__claim_id__get": {
    parameters: {
      path: {
        "claim_id": string;
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ClaimDetailRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "correct_candidate_projects__project_id__candidates__candidate_id__correction_post": {
    parameters: {
      path: {
        "candidate_id": string;
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["CatalogCorrectionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CatalogCorrectionRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_candidate_projects__project_id__preference_candidates_post": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["CandidateCreate"];
    } };
    responses: {
      "201": { content?: {
        "application/json": components["schemas"]["CandidateMutation"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_comparison_projects__project_id__comparisons_post": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ComparisonCreate"];
    } };
    responses: {
      "201": { content?: {
        "application/json": components["schemas"]["ComparisonRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_message_projects__project_id__messages_post": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["MessageCreate"];
    } };
    responses: {
      "202": { content?: {
        "application/json": components["schemas"]["MessageCreated"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json"?: undefined;
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_project_projects_post": {
    parameters: {
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ProjectCreate"];
    } };
    responses: {
      "201": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_requirement_projects__project_id__requirements_post": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "expected_version": number;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["RequirementCreate"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "create_research_projects__project_id__research_post": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ResearchCreate"];
    } };
    responses: {
      "202": { content?: {
        "application/json": components["schemas"]["ResearchCreated"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "delete_comparison_projects__project_id__comparisons__comparison_id__delete": {
    parameters: {
      path: {
        "comparison_id": string;
        "project_id": string;
      };
      query: {
        "expected_comparison_version": number;
        "expected_version": number;
      };
    };
    responses: {
      "204": { content?: {
        "application/json"?: undefined;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "delete_product_note_projects__project_id__products__project_product_id__notes_delete": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
      query: {
        "expected_version": number;
      };
    };
    responses: {
      "204": { content?: {
        "application/json"?: undefined;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "delete_project_note_projects__project_id__notes_delete": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "expected_version": number;
      };
    };
    responses: {
      "204": { content?: {
        "application/json"?: undefined;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "delete_project_projects__project_id__delete": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "expected_version": number;
      };
    };
    responses: {
      "204": { content?: {
        "application/json"?: undefined;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "delete_requirement_projects__project_id__requirements__requirement_id__delete": {
    parameters: {
      path: {
        "project_id": string;
        "requirement_id": string;
      };
      query: {
        "expected_version": number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "dismiss_candidate_profile_preference_candidates__candidate_id__dismiss_post": {
    parameters: {
      path: {
        "candidate_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["CandidateAction"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CandidateMutation"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "dismiss_proposal_projects__project_id__proposals__proposal_id__dismiss_post": {
    parameters: {
      path: {
        "project_id": string;
        "proposal_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProposalMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "favorite_product_saved_products__variant_id__favorite_put": {
    parameters: {
      path: {
        "variant_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["FavoriteCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["FavoriteRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_comparison_projects__project_id__comparisons__comparison_id__get": {
    parameters: {
      path: {
        "comparison_id": string;
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ComparisonRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_decision_projects__project_id__products__project_product_id__decision_get": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_product_note_projects__project_id__products__project_product_id__notes_get": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["NoteRead"] | null;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_product_products__product_id__get": {
    parameters: {
      path: {
        "product_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProductRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_profile_profile_get": {
    parameters: {
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProfileRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_project_note_projects__project_id__notes_get": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["NoteRead"] | null;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_project_projects__project_id__get": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_research_projects__project_id__research__research_run_id__get": {
    parameters: {
      path: {
        "project_id": string;
        "research_run_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ResearchRunRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "get_saved_product_saved_products__variant_id__get": {
    parameters: {
      path: {
        "variant_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["FavoriteRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "health_health_get": {
    parameters: {
    };
    responses: {
      "200": { content?: {
        "application/json": Record<string, string>;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_candidates_projects__project_id__candidates_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
        "run_id"?: null | string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CandidatePage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_catalog_variants_products_get": {
    parameters: {
      query: {
        "cursor"?: null | string;
        "limit"?: number;
        "q"?: string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CatalogVariantChoicePage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_comparisons_projects__project_id__comparisons_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ComparisonPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_conversations_projects__project_id__conversations_get": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ConversationPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_messages_projects__project_id__messages_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "before"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["MessagePage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_product_offers_products__product_id__offers_get": {
    parameters: {
      path: {
        "product_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
        "variant_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["OfferPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_project_products_projects__project_id__products_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectProductPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_projects_projects_get": {
    parameters: {
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_rejections_projects__project_id__rejections_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_requirements_projects__project_id__requirements_get": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": Array<components["schemas"]["RequirementRead"]>;
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_research_projects__project_id__research_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ResearchRunPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_saved_products_saved_products_get": {
    parameters: {
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["SavedProductPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "list_shortlist_projects__project_id__shortlist_get": {
    parameters: {
      path: {
        "project_id": string;
      };
      query: {
        "cursor"?: null | string;
        "limit"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionPage"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "mark_product_purchased_projects__project_id__products__project_product_id__purchased_post": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "normalize_candidate_projects__project_id__candidates__candidate_id__normalize_post": {
    parameters: {
      path: {
        "candidate_id": string;
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["NormalizeCandidateCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CatalogNormalizationRead"];
      } };
      "404": { content?: {
        "application/json"?: undefined;
      } };
      "409": { content?: {
        "application/json"?: undefined;
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "patch_comparison_projects__project_id__comparisons__comparison_id__patch": {
    parameters: {
      path: {
        "comparison_id": string;
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ComparisonPatch"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ComparisonRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "patch_preference_profile_preferences__preference_id__patch": {
    parameters: {
      path: {
        "preference_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["PreferencePatch"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProfileRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "patch_profile_profile_patch": {
    parameters: {
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ProfilePatch"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProfileRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "patch_project_projects__project_id__patch": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ProjectPatch"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "patch_requirement_projects__project_id__requirements__requirement_id__patch": {
    parameters: {
      path: {
        "project_id": string;
        "requirement_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["RequirementPatch"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "preference_suggestions_projects__project_id__preference_suggestions_get": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["PreferenceSuggestionsRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "product_research_projects__project_id__products__project_product_id__research_get": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
      query: {
        "assessment_offset"?: number;
        "claim_offset"?: number;
        "research_run_id"?: null | string;
        "source_offset"?: number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProjectProductResearchRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "product_sources_products__product_id__sources_get": {
    parameters: {
      path: {
        "product_id": string;
      };
      query: {
        "variant_id"?: null | string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProductSourcesRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "put_product_note_projects__project_id__products__project_product_id__notes_put": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["NoteWrite"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["NoteMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "put_project_note_projects__project_id__notes_put": {
    parameters: {
      path: {
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["NoteWrite"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["NoteMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "regenerate_comparison_projects__project_id__comparisons__comparison_id__regenerate_post": {
    parameters: {
      path: {
        "comparison_id": string;
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ComparisonRegenerate"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ComparisonRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "reject_product_projects__project_id__rejections__project_product_id__post": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "retry_research_projects__project_id__research__research_run_id__retry_post": {
    parameters: {
      path: {
        "project_id": string;
        "research_run_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["ResearchRetry"];
    } };
    responses: {
      "202": { content?: {
        "application/json": components["schemas"]["ResearchCreated"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "revert_candidate_correction_projects__project_id__candidates__candidate_id__correction_revert_post": {
    parameters: {
      path: {
        "candidate_id": string;
        "project_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["CatalogCorrectionRevertCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["CatalogCorrectionRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "revoke_preference_profile_preferences__preference_id__delete": {
    parameters: {
      path: {
        "preference_id": string;
      };
      query: {
        "expected_profile_version": number;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["ProfileRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "shortlist_product_projects__project_id__shortlist__project_product_id__post": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "source_snapshot_projects__project_id__sources__snapshot_id__get": {
    parameters: {
      path: {
        "project_id": string;
        "snapshot_id": string;
      };
    };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["SourceSnapshotRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "undo_product_purchased_projects__project_id__products__project_product_id__purchased_delete": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "undo_rejection_projects__project_id__rejections__project_product_id__delete": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "undo_shortlist_projects__project_id__shortlist__project_product_id__delete": {
    parameters: {
      path: {
        "project_id": string;
        "project_product_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["DecisionCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["DecisionMutationResult"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
  "unfavorite_product_saved_products__variant_id__favorite_delete": {
    parameters: {
      path: {
        "variant_id": string;
      };
    };
    requestBody: { content: {
      "application/json": components["schemas"]["FavoriteCommand"];
    } };
    responses: {
      "200": { content?: {
        "application/json": components["schemas"]["FavoriteRead"];
      } };
      "404": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "409": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
      "422": { content?: {
        "application/json": components["schemas"]["ApiErrorEnvelope"];
      } };
    };
  };
}
