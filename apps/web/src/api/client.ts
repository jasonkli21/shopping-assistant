import type { components } from "../../../../packages/api-types/src";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Project = components["schemas"]["ProjectRead"];
export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectPatch = components["schemas"]["ProjectPatch"];
export type ProjectPage = components["schemas"]["ProjectPage"];
export type Requirement = components["schemas"]["RequirementRead"];
export type RequirementCreate = components["schemas"]["RequirementCreate"];
export type RequirementPatch = components["schemas"]["RequirementPatch"];

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const payload: unknown = await response.json();
  if (!response.ok) {
    const envelope = payload as { error?: { code?: string; message?: string; details?: unknown } };
    throw new ApiRequestError(
      envelope.error?.message ?? `Request failed (${response.status})`,
      response.status,
      envelope.error?.code ?? "request_error",
      envelope.error?.details,
    );
  }
  return payload as T;
}

function jsonRequest(method: string, body?: unknown): RequestInit {
  return {
    method,
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  };
}

export const projectsApi = {
  list: (limit = 20, cursor?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<ProjectPage>(`/projects?${query.toString()}`);
  },
  create: (command: ProjectCreate) =>
    request<Project>("/projects", jsonRequest("POST", command)),
  get: (projectId: string) => request<Project>(`/projects/${projectId}`),
  patch: (projectId: string, command: ProjectPatch) =>
    request<Project>(`/projects/${projectId}`, jsonRequest("PATCH", command)),
  delete: (projectId: string, expectedVersion: number) =>
    request<void>(
      `/projects/${projectId}?${new URLSearchParams({ expected_version: String(expectedVersion) })}`,
      jsonRequest("DELETE"),
    ),
  listRequirements: (projectId: string) =>
    request<Requirement[]>(`/projects/${projectId}/requirements`),
  createRequirement: (projectId: string, expectedVersion: number, command: RequirementCreate) =>
    request<Project>(
      `/projects/${projectId}/requirements?${new URLSearchParams({ expected_version: String(expectedVersion) })}`,
      jsonRequest("POST", command),
    ),
  patchRequirement: (
    projectId: string,
    requirementId: string,
    command: RequirementPatch,
  ) =>
    request<Project>(
      `/projects/${projectId}/requirements/${requirementId}`,
      jsonRequest("PATCH", command),
    ),
  deleteRequirement: (projectId: string, requirementId: string, expectedVersion: number) =>
    request<Project>(
      `/projects/${projectId}/requirements/${requirementId}?${new URLSearchParams({ expected_version: String(expectedVersion) })}`,
      jsonRequest("DELETE"),
    ),
};
