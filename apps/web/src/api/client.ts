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
export type ResearchRunPage = components["schemas"]["ResearchRunPage"];
export type CandidateRead = components["schemas"]["CandidateRead"];
export type CandidatePage = components["schemas"]["CandidatePage"];
export type CatalogNormalizationRead = components["schemas"]["CatalogNormalizationRead"];
export type CatalogCorrectionCommand = components["schemas"]["CatalogCorrectionCommand"];
export type CatalogCorrectionRevertCommand = components["schemas"]["CatalogCorrectionRevertCommand"];
export type CatalogCorrectionRead = components["schemas"]["CatalogCorrectionRead"];
export type ProjectProductPage = components["schemas"]["ProjectProductPage"];
export type ProductRead = components["schemas"]["ProductRead"];
export type OfferPage = components["schemas"]["OfferPage"];
export type OfferRead = components["schemas"]["OfferRead"];
export type CatalogVariantChoicePage = components["schemas"]["CatalogVariantChoicePage"];
export type ProjectProductResearchRead = components["schemas"]["ProjectProductResearchRead"];
export type ClaimDetailRead = components["schemas"]["ClaimDetailRead"];
export type SourceSnapshotRead = components["schemas"]["SourceSnapshotRead"];
export type DecisionRead = components["schemas"]["DecisionRead"];
export type DecisionPage = components["schemas"]["DecisionPage"];
export type DecisionCommand = components["schemas"]["DecisionCommand"];
export type DecisionMutationResult = components["schemas"]["DecisionMutationResult"];
export type NoteRead = components["schemas"]["NoteRead"];
export type NoteWrite = components["schemas"]["NoteWrite"];
export type NoteMutationResult = components["schemas"]["NoteMutationResult"];
export type ComparisonRead = components["schemas"]["ComparisonRead"];
export type ComparisonPage = components["schemas"]["ComparisonPage"];
export type ComparisonCreate = components["schemas"]["ComparisonCreate"];
export type ComparisonPatch = components["schemas"]["ComparisonPatch"];
export type ComparisonDimension = components["schemas"]["ComparisonDimensionInput"];
export type FavoriteRead = components["schemas"]["FavoriteRead"];
export type SavedProductPage = components["schemas"]["SavedProductPage"];
export type ProfileRead = components["schemas"]["ProfileRead"];
export type PreferenceRead = components["schemas"]["PreferenceRead"];
export type PreferenceCandidateRead = components["schemas"]["PreferenceCandidateRead"];
export type CandidateMutation = components["schemas"]["CandidateMutation"];
export type CandidateCreate = components["schemas"]["CandidateCreate"];
export type PreferencePatch = components["schemas"]["PreferencePatch"];
export type PreferenceSuggestionsRead = components["schemas"]["PreferenceSuggestionsRead"];

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

export const preferencesApi = {
  profile: () => request<ProfileRead>("/profile"),
  patchProfile: (command: { expected_version: number; reuse_enabled: boolean }) =>
    request<ProfileRead>("/profile", jsonRequest("PATCH", command)),
  createCandidate: (projectId: string, command: CandidateCreate) =>
    request<CandidateMutation>(
      `/projects/${projectId}/preference-candidates`,
      jsonRequest("POST", command),
    ),
  acceptCandidate: (candidateId: string, expectedProfileVersion: number) =>
    request<CandidateMutation>(
      `/profile/preference-candidates/${candidateId}/accept`,
      jsonRequest("POST", { expected_profile_version: expectedProfileVersion }),
    ),
  dismissCandidate: (candidateId: string, expectedProfileVersion: number) =>
    request<CandidateMutation>(
      `/profile/preference-candidates/${candidateId}/dismiss`,
      jsonRequest("POST", { expected_profile_version: expectedProfileVersion }),
    ),
  patchPreference: (preferenceId: string, command: PreferencePatch) =>
    request<ProfileRead>(
      `/profile/preferences/${preferenceId}`,
      jsonRequest("PATCH", command),
    ),
  revokePreference: (preferenceId: string, expectedProfileVersion: number) =>
    request<ProfileRead>(
      `/profile/preferences/${preferenceId}?${new URLSearchParams({ expected_profile_version: String(expectedProfileVersion) })}`,
      jsonRequest("DELETE"),
    ),
  suggestions: (projectId: string) =>
    request<PreferenceSuggestionsRead>(`/projects/${projectId}/preference-suggestions`),
  applyToProject: (projectId: string, preferenceId: string, expectedProjectVersion: number) =>
    request<Project>(
      `/projects/${projectId}/preferences/${preferenceId}/apply?${new URLSearchParams({ expected_project_version: String(expectedProjectVersion) })}`,
      jsonRequest("POST"),
    ),
};

export const researchApi = {
  productEvidence: (projectId: string, projectProductId: string, assessmentOffset = 0, researchRunId?: string, claimOffset = 0, sourceOffset = 0, signal?: AbortSignal) => {
    const query = new URLSearchParams({
      assessment_offset: String(assessmentOffset),
      claim_offset: String(claimOffset),
      source_offset: String(sourceOffset),
    });
    if (researchRunId) query.set("research_run_id", researchRunId);
    return request<ProjectProductResearchRead>(
      `/projects/${projectId}/products/${projectProductId}/research?${query.toString()}`, { signal },
    );
  },
  claim: (projectId: string, claimId: string, signal?: AbortSignal) =>
    request<ClaimDetailRead>(`/projects/${projectId}/claims/${claimId}`, { signal }),
  source: (projectId: string, snapshotId: string, signal?: AbortSignal) =>
    request<SourceSnapshotRead>(`/projects/${projectId}/sources/${snapshotId}`, { signal }),
  create: (projectId: string, command: ResearchCreate) =>
    request<ResearchCreated>(
      `/projects/${projectId}/research`,
      jsonRequest("POST", command),
    ),
  list: (projectId: string, limit = 20, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<ResearchRunPage>(
      `/projects/${projectId}/research?${query.toString()}`,
      { signal },
    );
  },
  get: (projectId: string, runId: string, signal?: AbortSignal) =>
    request<ResearchRunRead>(`/projects/${projectId}/research/${runId}`, { signal }),
  cancel: (projectId: string, runId: string) =>
    request<{ run: ResearchRunRead; replayed: boolean }>(
      `/projects/${projectId}/research/${runId}/cancel`,
      jsonRequest("POST"),
    ),
  retry: (projectId: string, runId: string, command: { request_key: string; expected_version: number }) =>
    request<ResearchCreated>(
      `/projects/${projectId}/research/${runId}/retry`,
      jsonRequest("POST", command),
    ),
  candidates: (
    projectId: string,
    runId: string,
    limit = 20,
    cursor?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ limit: String(limit), run_id: runId });
    if (cursor) query.set("cursor", cursor);
    return request<CandidatePage>(`/projects/${projectId}/candidates?${query.toString()}`, {
      signal,
    });
  },
};

export const catalogApi = {
  listProjectProducts: (projectId: string, limit = 20, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<ProjectProductPage>(
      `/projects/${projectId}/products?${query.toString()}`,
      { signal },
    );
  },
  listVariants: (queryText = "", limit = 20, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ q: queryText, limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<CatalogVariantChoicePage>(`/products?${query.toString()}`, { signal });
  },
  getProduct: (productId: string, signal?: AbortSignal) =>
    request<ProductRead>(`/products/${productId}`, { signal }),
  offers: (
    productId: string,
    variantId: string,
    limit = 20,
    cursor?: string,
    signal?: AbortSignal,
  ) => {
    const query = new URLSearchParams({ variant_id: variantId, limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<OfferPage>(`/products/${productId}/offers?${query.toString()}`, { signal });
  },
  normalizeCandidate: (
    projectId: string,
    candidateId: string,
    command: {
      request_key: string;
      expected_catalog_version: number;
      expected_project_version: number;
    },
  ) =>
    request<CatalogNormalizationRead>(
      `/projects/${projectId}/candidates/${candidateId}/normalize`,
      jsonRequest("POST", command),
    ),
  correctCandidate: (
    projectId: string,
    candidateId: string,
    command: CatalogCorrectionCommand,
  ) =>
    request<CatalogCorrectionRead>(
      `/projects/${projectId}/candidates/${candidateId}/correction`,
      jsonRequest("POST", command),
    ),
  revertCandidateCorrection: (
    projectId: string,
    candidateId: string,
    command: CatalogCorrectionRevertCommand,
  ) =>
    request<CatalogCorrectionRead>(
      `/projects/${projectId}/candidates/${candidateId}/correction/revert`,
      jsonRequest("POST", command),
    ),
  listSavedProducts: (limit = 20, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<SavedProductPage>(`/saved-products?${query.toString()}`, { signal });
  },
  favorite: (variantId: string, expectedVersion: number) =>
    request<FavoriteRead>(
      `/saved-products/${variantId}/favorite`,
      jsonRequest("PUT", { expected_version: expectedVersion }),
    ),
  unfavorite: (variantId: string, expectedVersion: number) =>
    request<FavoriteRead>(
      `/saved-products/${variantId}/favorite`,
      jsonRequest("DELETE", { expected_version: expectedVersion }),
    ),
  favoriteState: (variantId: string, signal?: AbortSignal) =>
    request<FavoriteRead>(`/saved-products/${variantId}`, { signal }),
};

export const decisionsApi = {
  listShortlist: (projectId: string, limit = 50, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<DecisionPage>(`/projects/${projectId}/shortlist?${query.toString()}`, { signal });
  },
  listRejections: (projectId: string, limit = 50, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<DecisionPage>(`/projects/${projectId}/rejections?${query.toString()}`, { signal });
  },
  get: (projectId: string, projectProductId: string, signal?: AbortSignal) =>
    request<DecisionRead>(
      `/projects/${projectId}/products/${projectProductId}/decision`,
      { signal },
    ),
  shortlist: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/shortlist/${projectProductId}`,
      jsonRequest("POST", command),
    ),
  undoShortlist: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/shortlist/${projectProductId}`,
      jsonRequest("DELETE", command),
    ),
  reject: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/rejections/${projectProductId}`,
      jsonRequest("POST", command),
    ),
  undoRejection: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/rejections/${projectProductId}`,
      jsonRequest("DELETE", command),
    ),
  purchased: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/products/${projectProductId}/purchased`,
      jsonRequest("POST", command),
    ),
  undoPurchased: (projectId: string, projectProductId: string, command: DecisionCommand) =>
    request<DecisionMutationResult>(
      `/projects/${projectId}/products/${projectProductId}/purchased`,
      jsonRequest("DELETE", command),
    ),
};

export const notesApi = {
  get: (projectId: string, projectProductId?: string, signal?: AbortSignal) =>
    request<NoteRead | null>(
      projectProductId
        ? `/projects/${projectId}/products/${projectProductId}/notes`
        : `/projects/${projectId}/notes`,
      { signal },
    ),
  put: (projectId: string, command: NoteWrite, projectProductId?: string) =>
    request<NoteMutationResult>(
      projectProductId
        ? `/projects/${projectId}/products/${projectProductId}/notes`
        : `/projects/${projectId}/notes`,
      jsonRequest("PUT", command),
    ),
  delete: (projectId: string, expectedVersion: number, projectProductId?: string) => {
    const path = projectProductId
      ? `/projects/${projectId}/products/${projectProductId}/notes`
      : `/projects/${projectId}/notes`;
    return request<void>(
      `${path}?${new URLSearchParams({ expected_version: String(expectedVersion) })}`,
      jsonRequest("DELETE"),
    );
  },
};

export const comparisonsApi = {
  create: (projectId: string, command: ComparisonCreate) =>
    request<ComparisonRead>(
      `/projects/${projectId}/comparisons`,
      jsonRequest("POST", command),
    ),
  list: (projectId: string, limit = 20, cursor?: string, signal?: AbortSignal) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor) query.set("cursor", cursor);
    return request<ComparisonPage>(
      `/projects/${projectId}/comparisons?${query.toString()}`,
      { signal },
    );
  },
  get: (projectId: string, comparisonId: string, signal?: AbortSignal) =>
    request<ComparisonRead>(
      `/projects/${projectId}/comparisons/${comparisonId}`,
      { signal },
    ),
  update: (projectId: string, comparisonId: string, command: ComparisonPatch) =>
    request<ComparisonRead>(
      `/projects/${projectId}/comparisons/${comparisonId}`,
      jsonRequest("PATCH", command),
    ),
  regenerate: (projectId: string, comparisonId: string, expectedVersion: number, expectedComparisonVersion: number) =>
    request<ComparisonRead>(
      `/projects/${projectId}/comparisons/${comparisonId}/regenerate`,
      jsonRequest("POST", {
        expected_version: expectedVersion,
        expected_comparison_version: expectedComparisonVersion,
      }),
    ),
  delete: (projectId: string, comparisonId: string, expectedVersion: number, expectedComparisonVersion: number) =>
    request<void>(
      `/projects/${projectId}/comparisons/${comparisonId}?${new URLSearchParams({
        expected_version: String(expectedVersion),
        expected_comparison_version: String(expectedComparisonVersion),
      })}`,
      jsonRequest("DELETE"),
    ),
};
