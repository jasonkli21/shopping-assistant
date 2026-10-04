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
