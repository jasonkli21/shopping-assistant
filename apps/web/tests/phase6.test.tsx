import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Project } from "../src/api/client";
import { ComparisonPage } from "../src/features/comparisons/ComparisonPage";
import { ProductDecisionActions } from "../src/features/decisions/ProductDecisionActions";
import { UserNoteEditor } from "../src/features/decisions/UserNoteEditor";
import { FavoriteButton } from "../src/features/products/FavoriteButton";

const projectId = "d0f2e0d1-9013-4dad-ae81-cbe6e9b393a4";
const firstProductId = "8e53a411-c7a9-4b57-b8c6-168b52a4c79a";
const secondProductId = "a9201a43-b424-4bb7-8ba8-643871568f46";
const variantId = "98a83acf-c4dc-485c-916a-534a72da4d1e";
const timestamp = "2026-10-03T12:00:00Z";

const project: Project = {
  id: projectId,
  title: "Apartment vacuum",
  goal: "Find a compact vacuum",
  category: "vacuum",
  status: "active",
  budget_target: null,
  budget_maximum: null,
  budget_currency: null,
  notes: null,
  revision: 1,
  created_at: timestamp,
  updated_at: timestamp,
  requirements: [],
};

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function renderWithQuery(element: ReactNode, initialPath = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/projects/:projectId/compare" element={element} />
          <Route path="/" element={element} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Phase 6 decision workspace", () => {
  it("keeps a failed note draft in place for retry", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname.endsWith("/notes") && !init?.method) return response(null);
      if (url.pathname.endsWith("/notes") && init?.method === "PUT") {
        return response({ error: { code: "temporary_failure", message: "Note service is unavailable." } }, 503);
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<UserNoteEditor project={project} projectProductId={firstProductId} />);

    const note = await screen.findByRole("textbox");
    fireEvent.change(note, { target: { value: "Check filter replacement cost." } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Note service is unavailable.");
    expect(note).toHaveValue("Check filter replacement cost.");
    expect(screen.getByRole("button", { name: "Save note" })).toBeEnabled();
  });

  it("saves a favorite independently from a project decision", async () => {
    let favorite = false;
    let version = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === `/saved-products/${variantId}` && !init?.method) {
        return response({ variant_id: variantId, favorite, version });
      }
      if (url.pathname.endsWith("/favorite") && init?.method === "PUT") {
        favorite = true;
        version += 1;
        return response({ variant_id: variantId, favorite, version });
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<FavoriteButton variantId={variantId} />);

    const save = await screen.findByRole("button", { name: "Save to favorites" });
    fireEvent.click(save);
    const saved = await screen.findByRole("button", { name: "Remove from Saved Products" });
    expect(saved).toHaveAttribute("aria-pressed", "true");
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true);
  });

  it("records shortlist transitions against an exact project variant", async () => {
    let state = "considering";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === `/projects/${projectId}/products/${firstProductId}/decision`) {
        return response({
          project_product_id: firstProductId,
          state,
          reason: "",
          rejection_reason: null,
          concerns: [],
          selected_offer_id: null,
          version: state === "considering" ? 1 : 2,
          updated_at: null,
          events: [],
        });
      }
      if (url.pathname === `/projects/${projectId}/shortlist/${firstProductId}` && init?.method === "POST") {
        state = "shortlisted";
        return response({ replayed: false, event: { to_state: state } });
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<ProductDecisionActions project={project} projectProductId={firstProductId} />);

    fireEvent.click(await screen.findByRole("button", { name: "Shortlist" }));
    await waitFor(() => expect(screen.getByText("shortlisted")).toBeInTheDocument());
    const command = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(command).toBeDefined();
    expect(JSON.parse(String(command?.[1]?.body))).toMatchObject({
      expected_version: 1,
      reason: "",
    });
  });

  it("preserves exact-variant selection when a comparison save conflicts", async () => {
    const products = [
      {
        id: firstProductId,
        project_id: projectId,
        product_id: "b5bc9268-f936-4408-8ae8-f4e53c82486b",
        variant_id: variantId,
        canonical_name: "Vacuum One",
        brand: "Example",
        category: "vacuum",
        model_family: "One",
        variant_name: "US, blue",
        identity_attributes: { region: { value: "US" } },
        category_attributes: {},
        first_candidate_id: null,
        discovery_reason: "Example candidate",
        created_at: timestamp,
        offers: [],
      },
      {
        id: secondProductId,
        project_id: projectId,
        product_id: "f7777a83-0ea8-4bc8-a728-138834bbd8aa",
        variant_id: "26d811ea-f52c-46db-92d2-18a4b44337a8",
        canonical_name: "Vacuum Two",
        brand: "Example",
        category: "vacuum",
        model_family: "Two",
        variant_name: "US, green",
        identity_attributes: { region: { value: "US" } },
        category_attributes: {},
        first_candidate_id: null,
        discovery_reason: "Example candidate",
        created_at: timestamp,
        offers: [],
      },
    ];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === `/projects/${projectId}` && !init?.method) return response(project);
      if (url.pathname === `/projects/${projectId}/products`) {
        return response({ items: products, next_cursor: null, catalog_version: 1, project_version: 1 });
      }
      if (url.pathname === `/projects/${projectId}/comparisons`) {
        if (init?.method === "POST") {
          return response({ error: { code: "revision_conflict", message: "Project changed." } }, 409);
        }
        return response({ items: [], next_cursor: null });
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<ComparisonPage />, `/projects/${projectId}/compare`);

    const choices = await screen.findAllByRole("checkbox");
    fireEvent.click(choices[0]);
    fireEvent.click(choices[1]);
    fireEvent.click(screen.getByRole("button", { name: "Save comparison" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Project changed.");
    await waitFor(() => {
      expect(choices[0]).toBeChecked();
      expect(choices[1]).toBeChecked();
    });
    const createRequest = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(createRequest).toBeDefined();
    expect(JSON.parse(String(createRequest?.[1]?.body))).toMatchObject({
      project_product_ids: [firstProductId, secondProductId],
      expected_version: 1,
    });
  });
});
