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
    MessageCreate: {
      "text": string;
      "request_key": string;
      "expected_version": number;
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
      "created_at": string;
      "completed_at": null | string;
      "proposal"?: components["schemas"]["ProposalRead"] | null;
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
      "created_at": string;
      "updated_at": string;
    };
  };
}

export interface paths {
  "/health": {
    "get": operations["health_health_get"];
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
  "/projects/{project_id}/proposals/{proposal_id}/apply": {
    "post": operations["apply_proposal_projects__project_id__proposals__proposal_id__apply_post"];
  };
  "/projects/{project_id}/proposals/{proposal_id}/dismiss": {
    "post": operations["dismiss_proposal_projects__project_id__proposals__proposal_id__dismiss_post"];
  };
  "/projects/{project_id}/requirements": {
    "get": operations["list_requirements_projects__project_id__requirements_get"];
    "post": operations["create_requirement_projects__project_id__requirements_post"];
  };
  "/projects/{project_id}/requirements/{requirement_id}": {
    "delete": operations["delete_requirement_projects__project_id__requirements__requirement_id__delete"];
    "patch": operations["patch_requirement_projects__project_id__requirements__requirement_id__patch"];
  };
}

export interface operations {
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
}
