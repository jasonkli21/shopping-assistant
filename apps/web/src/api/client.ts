import type { components } from "../../../../packages/api-types/src";
import { consumeAssistantSse, type AssistantSseEvent } from "../features/assistant/sse";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

export type Project = components["schemas"]["ProjectRead"];
export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectPatch = components["schemas"]["ProjectPatch"];
export type ProjectPage = components["schemas"]["ProjectPage"];
export type Requirement = components["schemas"]["RequirementRead"];
export type RequirementCreate = components["schemas"]["RequirementCreate"];
export type RequirementPatch = components["schemas"]["RequirementPatch"];
export type ConversationRead = components["schemas"]["ConversationRead"];
export type ConversationPage = components["schemas"]["ConversationPage"];
export type MessageCreate = components["schemas"]["MessageCreate"];
export type MessageCreated = components["schemas"]["MessageCreated"];
export type MessageRead = components["schemas"]["MessageRead"];
export type MessagePage = components["schemas"]["MessagePage"];
export type ProposalRead = components["schemas"]["ProposalRead"];
export type ProposalMutationResult = components["schemas"]["ProposalMutationResult"];
export type ResearchCreate = components["schemas"]["ResearchCreate"];
export type ResearchCreated = components["schemas"]["ResearchCreated"];
export type ResearchRunRead = components["schemas"]["ResearchRunRead"];
export type CandidateRead = components["schemas"]["CandidateRead"];
export type CandidatePage = components["schemas"]["CandidatePage"];

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
  get: (projectId: string, signal?: AbortSignal) =>
    request<Project>(`/projects/${projectId}`, { signal }),
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
  listConversations: (projectId: string) =>
    request<ConversationPage>(`/projects/${projectId}/conversations`),
  listMessages: (projectId: string, limit = 50, before?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (before) query.set("before", before);
    return request<MessagePage>(`/projects/${projectId}/messages?${query.toString()}`);
  },
  createMessage: (projectId: string, command: MessageCreate) =>
    request<MessageCreated>(`/projects/${projectId}/messages`, jsonRequest("POST", command)),
  streamMessage: async (
    projectId: string,
    messageId: string,
    onEvent: (event: AssistantSseEvent) => void,
    signal: AbortSignal,
  ) => {
    const query = new URLSearchParams({ message_id: messageId });
    const response = await fetch(
      `${API_BASE_URL}/projects/${projectId}/messages/stream?${query.toString()}`,
      { headers: { Accept: "text/event-stream" }, signal },
    );
    if (!response.ok) {
      const payload = (await response.json().catch(() => ({}))) as {
        error?: { code?: string; message?: string; details?: unknown };
      };
      throw new ApiRequestError(
        payload.error?.message ?? `Assistant stream failed (${response.status})`,
        response.status,
        payload.error?.code ?? "stream_error",
        payload.error?.details,
      );
    }
    return consumeAssistantSse(response, onEvent);
  },
  applyProposal: (
    projectId: string,
    proposalId: string,
    expectedVersion: number,
  ) =>
    request<ProposalMutationResult>(
      `/projects/${projectId}/proposals/${proposalId}/apply`,
      jsonRequest("POST", { expected_version: expectedVersion }),
    ),
  dismissProposal: (projectId: string, proposalId: string) =>
    request<ProposalMutationResult>(
      `/projects/${projectId}/proposals/${proposalId}/dismiss`,
      jsonRequest("POST"),
    ),
};

export const researchApi = {
  create: (projectId: string, command: ResearchCreate) =>
    request<ResearchCreated>(
      `/projects/${projectId}/research`,
      jsonRequest("POST", command),
    ),
  list: (projectId: string, limit = 20, signal?: AbortSignal) =>
    request<{ items: ResearchRunRead[] }>(
      `/projects/${projectId}/research?${new URLSearchParams({ limit: String(limit) })}`,
      { signal },
    ),
  get: (projectId: string, runId: string, signal?: AbortSignal) =>
    request<ResearchRunRead>(`/projects/${projectId}/research/${runId}`, { signal }),
  cancel: (projectId: string, runId: string) =>
    request<{ run: ResearchRunRead; replayed: boolean }>(
      `/projects/${projectId}/research/${runId}/cancel`,
      jsonRequest("POST"),
    ),
  candidates: (projectId: string, limit = 50, signal?: AbortSignal) =>
    request<CandidatePage>(
      `/projects/${projectId}/candidates?${new URLSearchParams({ limit: String(limit) })}`,
      { signal },
    ),
};
