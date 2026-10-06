import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type {
  CandidateMutation,
  Project,
  PreferenceCandidateRead,
  PreferenceRead,
  ProfileRead,
} from "../src/api/client";
import { PreferenceProfilePage } from "../src/features/preferences/PreferenceProfilePage";
import { PreferencePromotionAction } from "../src/features/preferences/PreferencePromotionAction";

const projectId = "d2cf6497-9e70-41b6-844d-418320c3ea18";
const candidateId = "a2cf6497-9e70-41b6-844d-418320c3ea18";
const preferenceId = "b2cf6497-9e70-41b6-844d-418320c3ea18";
const now = "2026-10-05T12:00:00Z";

function candidate(status: PreferenceCandidateRead["status"] = "pending"): PreferenceCandidateRead {
  return {
    id: candidateId,
    source_kind: "requirement",
    source_project_id: projectId,
    source_requirement_id: "c2cf6497-9e70-41b6-844d-418320c3ea18",
    source_project_product_id: null,
    source_decision_id: null,
    source_project_revision: 2,
    source_project_title: "Compact sofa",
    source_available: true,
    source_stale: false,
    label: "Prefers compact furniture",
    key: "statement",
    operator: null,
    value: "prefers compact furniture",
    unit: "",
    monetary: false,
    category_scopes: ["furniture"],
    rationale: "Explicitly selected from this project.",
    status,
    created_at: now,
    resolved_at: status === "pending" ? null : now,
  };
}

function preference(status: PreferenceRead["status"] = "active", label = "Prefers compact furniture"): PreferenceRead {
  return {
    id: preferenceId,
    source_kind: "requirement",
    source_candidate_id: candidateId,
    source_project_id: projectId,
    source_requirement_id: "c2cf6497-9e70-41b6-844d-418320c3ea18",
    source_project_product_id: null,
    source_decision_id: null,
    source_project_title: "Compact sofa",
    source_available: true,
    key: "statement",
    operator: null,
    value: "prefers compact furniture",
    unit: "",
    monetary: false,
    category_scopes: ["furniture"],
    label,
    strength: "soft",
    status,
    revision: label === "Prefers compact furniture" ? 1 : 2,
    accepted_at: now,
    updated_at: now,
  };
}

function profile(overrides: Partial<ProfileRead> = {}): ProfileRead {
  return {
    id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
    revision: 2,
    reuse_enabled: true,
    preferences: [],
    candidates: [candidate()],
    updated_at: now,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderProfile() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/profile"]}><PreferenceProfilePage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("shopping profile", () => {
  it("accepts an explicit candidate and revokes it from future reuse", async () => {
    let stored = profile();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/profile") && method === "GET") return jsonResponse(stored);
      if (url.includes(`/profile/preference-candidates/${candidateId}/accept`)) {
        const mutation: CandidateMutation = { candidate: candidate("accepted"), preference: preference(), replayed: false };
        stored = profile({ revision: 3, candidates: [candidate("accepted")], preferences: [preference()] });
        return jsonResponse(mutation);
      }
      if (url.includes(`/profile/preferences/${preferenceId}`) && method === "DELETE") {
        stored = profile({ revision: 4, candidates: [candidate("accepted")], preferences: [preference("revoked")] });
        return jsonResponse(stored);
      }
      throw new Error(`Unexpected request: ${method} ${url}`);
    }));

    renderProfile();
    fireEvent.click(await screen.findByRole("button", { name: "Accept into profile" }));
    await screen.findByRole("button", { name: "Revoke" });
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(screen.getAllByText("revoked").length).toBeGreaterThan(0));
    expect(screen.getByText(/External Personal AI memory is unavailable/)).toBeInTheDocument();
  });

  it("creates a pending candidate from a rejected product only after explicit selection", async () => {
    const project = { id: projectId, revision: 3, category: "office" } as Project;
    const calls: Array<{ url: string; body: unknown }> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      if (url.endsWith("/profile") && method === "GET") return jsonResponse(profile({ candidates: [] }));
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return jsonResponse({ candidate: candidate(), replayed: false }, 201);
    });
    vi.stubGlobal("fetch", fetchMock);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <PreferencePromotionAction
            project={project}
            sourceProjectProductId="f2cf6497-9e70-41b6-844d-418320c3ea18"
            initialLabel="Avoid a rejected desk"
            initialValue="avoid this rejected desk"
            initialRationale="Selected from an explicit product rejection."
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByText("Propose as a shopping preference"));
    const submit = await screen.findByRole("button", { name: "Save candidate for review" });
    await waitFor(() => expect(submit).toBeEnabled());
    fireEvent.click(submit);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toContain(`/projects/${projectId}/preference-candidates`);
    expect(calls[0].body).toMatchObject({
      expected_project_version: 3,
      source_project_product_id: "f2cf6497-9e70-41b6-844d-418320c3ea18",
      category_scopes: ["office"],
    });
    expect(calls[0].body).not.toHaveProperty("source_requirement_id");
    expect(calls.some(({ url }) => url.includes("/accept"))).toBe(false);
  });
});
