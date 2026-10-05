import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Project, ProposalRead } from "../src/api/client";
import { ProposalCard } from "../src/features/assistant/ProposalCard";
import { ComparisonPage } from "../src/features/comparisons/ComparisonPage";
import { ProductDecisionActions } from "../src/features/decisions/ProductDecisionActions";
import { UserNoteEditor } from "../src/features/decisions/UserNoteEditor";
import { FavoriteButton } from "../src/features/products/FavoriteButton";

const projectId = "d0f2e0d1-9013-4dad-ae81-cbe6e9b393a4";
const firstProductId = "8e53a411-c7a9-4b57-b8c6-168b52a4c79a";
const secondProductId = "a9201a43-b424-4bb7-8ba8-643871568f46";
const variantId = "98a83acf-c4dc-485c-916a-534a72da4d1e";
const savedOfferId = "f4d0a702-6c02-4c27-8e45-7cfebd233cd8";
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
          <Route path="/projects/:projectId/compare/:comparisonId" element={element} />
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
  it("previews every assistant decision operation before enabling apply", () => {
    const proposal: ProposalRead = {
      id: "aa2d5c77-62b1-4da1-adf3-05ea82e76d23",
      project_id: projectId,
      assistant_message_id: "ba2d5c77-62b1-4da1-adf3-05ea82e76d23",
      base_revision: project.revision,
      schema_version: 2,
      operations: {
        project_updates: {},
        requirement_operations: [],
        decision_operations: [
          { operation: "shortlist", project_product_id: firstProductId, reason: "Good warranty", concerns: ["Noise"] },
          { operation: "reject", project_product_id: secondProductId, rejection_reason: "too_expensive", reason: "Over budget", concerns: [] },
          { operation: "add_note", project_product_id: firstProductId, text: "Check replacement filter cost." },
          {
            operation: "set_comparison_dimensions",
            project_product_ids: [firstProductId, secondProductId],
            dimensions: [{ key: "warranty", label: "Warranty", unit: "years", dimension_type: "evidence" }],
            title: "Vacuum warranty comparison",
            display_mode: "differences",
          },
        ],
      },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    render(<ProposalCard proposal={proposal} project={project} pending={false} blocked={false} onApply={vi.fn()} onDismiss={vi.fn()} />);

    expect(screen.getByText(`Project variant ${firstProductId}`)).toBeInTheDocument();
    expect(screen.getByText(`Project variant ${secondProductId}`)).toBeInTheDocument();
    expect(screen.getByText("Reason: Good warranty")).toBeInTheDocument();
    expect(screen.getByText("Reject variant · Too Expensive")).toBeInTheDocument();
    expect(screen.getByText("Check replacement filter cost.")).toBeInTheDocument();
    expect(screen.getByText("Vacuum warranty comparison")).toBeInTheDocument();
    expect(screen.getByText("Variants: " + firstProductId + " · " + secondProductId)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply suggestion" })).toBeEnabled();
  });

  it("blocks confirmation when an assistant operation cannot be previewed", () => {
    const proposal: ProposalRead = {
      id: "aa2d5c77-62b1-4da1-adf3-05ea82e76d23",
      project_id: projectId,
      assistant_message_id: "ba2d5c77-62b1-4da1-adf3-05ea82e76d23",
      base_revision: project.revision,
      schema_version: 2,
      operations: { project_updates: {}, requirement_operations: [], decision_operations: [{ operation: "delete_project" }] },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    render(<ProposalCard proposal={proposal} project={project} pending={false} blocked={false} onApply={vi.fn()} onDismiss={vi.fn()} />);

    expect(screen.getByRole("alert")).toHaveTextContent("cannot be previewed safely");
    expect(screen.getByRole("button", { name: "Apply suggestion" })).toBeDisabled();
  });

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
          reason: "Preserve the fit rationale.",
          rejection_reason: null,
          concerns: ["Storage is limited"],
          selected_offer_id: savedOfferId,
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
    renderWithQuery(<ProductDecisionActions
      project={project}
      projectProductId={firstProductId}
      offers={[{
        id: savedOfferId,
        variant_id: variantId,
        observation_id: null,
        retailer_name: "Example retailer",
        retailer_domain: "example.test",
        url: "https://example.test/vacuum",
        amount: "299.00",
        currency: "USD",
        availability: "in_stock",
        condition: "new",
        observed_at: timestamp,
      }]}
    />);

    fireEvent.click(await screen.findByRole("button", { name: "Shortlist" }));
    await waitFor(() => expect(screen.getByText("shortlisted")).toBeInTheDocument());
    const command = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(command).toBeDefined();
    expect(JSON.parse(String(command?.[1]?.body))).toMatchObject({
      expected_version: 1,
      reason: "Preserve the fit rationale.",
      concerns: ["Storage is limited"],
      selected_offer_id: savedOfferId,
    });
  });

  it("lets the owner deliberately edit decision concerns and selected offer", async () => {
    const alternativeOfferId = "da13248c-4e2c-4c2c-8196-d4bd1cd93773";
    let state = "considering";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === `/projects/${projectId}/products/${firstProductId}/decision`) {
        return response({
          project_product_id: firstProductId,
          state,
          reason: "Saved rationale",
          rejection_reason: null,
          concerns: ["Original concern"],
          selected_offer_id: savedOfferId,
          version: state === "considering" ? 1 : 2,
          updated_at: null,
          events: [],
        });
      }
      if (url.pathname === `/projects/${projectId}/shortlist/${firstProductId}` && init?.method === "POST") {
        state = "shortlisted";
        return response({ replayed: false, event: { to_state: state } });
      }
      if (url.pathname === `/projects/${projectId}/products/${firstProductId}/decision` && init?.method === "POST") {
        return response({ error: { code: "unexpected_route", message: "Unexpected decision route." } }, 500);
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<ProductDecisionActions
      project={project}
      projectProductId={firstProductId}
      offers={[
        {
          id: savedOfferId,
          variant_id: variantId,
          observation_id: null,
          retailer_name: "Example retailer",
          retailer_domain: "example.test",
          url: "https://example.test/vacuum",
          amount: "299.00",
          currency: "USD",
          availability: "in_stock",
          condition: "new",
          observed_at: timestamp,
        },
        {
          id: alternativeOfferId,
          variant_id: variantId,
          observation_id: null,
          retailer_name: "Alternative retailer",
          retailer_domain: "alternative.test",
          url: "https://alternative.test/vacuum",
          amount: "319.00",
          currency: "USD",
          availability: "in_stock",
          condition: "new",
          observed_at: timestamp,
        },
      ]}
    />);

    fireEvent.change(await screen.findByLabelText(/Concerns/), { target: { value: "Updated concern\nNoise" } });
    fireEvent.change(screen.getByLabelText("Selected offer"), { target: { value: alternativeOfferId } });
    fireEvent.click(screen.getByRole("button", { name: "Shortlist" }));
    await waitFor(() => expect(screen.getByText("shortlisted")).toBeInTheDocument());
    const command = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(String(command?.[1]?.body))).toMatchObject({
      concerns: ["Updated concern", "Noise"],
      selected_offer_id: alternativeOfferId,
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

  it("sends only changed display and title fields for a saved comparison", async () => {
    const comparisonId = "21b6b31d-fd60-42c4-9af3-3c80cf1291d6";
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
        identity_attributes: {},
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
        identity_attributes: {},
        category_attributes: {},
        first_candidate_id: null,
        discovery_reason: "Example candidate",
        created_at: timestamp,
        offers: [],
      },
    ];
    const dimension = {
      key: "warranty",
      label: "Warranty",
      unit: "years",
      dimension_type: "evidence",
      equal: false,
      cells: [
        { project_product_id: firstProductId, status: "known", value: [], unit: null, comparison_value: null, provenance: {} },
        { project_product_id: secondProductId, status: "unknown", value: null, unit: null, comparison_value: null, provenance: {} },
      ],
    };
    let comparison: Record<string, unknown> = {
      id: comparisonId,
      project_id: projectId,
      title: "Saved vacuum comparison",
      display_mode: "all",
      comparison_revision: 1,
      project_revision: 1,
      snapshot_id: "31b6b31d-fd60-42c4-9af3-3c80cf1291d6",
      generated_at: timestamp,
      stale: false,
      products: products.map((item) => ({
        project_product_id: item.id,
        product_id: item.product_id,
        variant_id: item.variant_id,
        canonical_name: item.canonical_name,
        brand: item.brand,
        category: item.category,
        variant_name: item.variant_name,
        identity_attributes: {},
        product_revision: 1,
        variant_revision: 1,
      })),
      dimensions: [dimension],
      definition_dimensions: [dimension],
      hidden_equal_dimensions: 0,
    };
    const updates: Array<Record<string, unknown>> = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === `/projects/${projectId}` && !init?.method) return response(project);
      if (url.pathname === `/projects/${projectId}/products`) {
        return response({ items: products, next_cursor: null, catalog_version: 1, project_version: 1 });
      }
      if (url.pathname === `/projects/${projectId}/comparisons` && !init?.method) {
        return response({ items: [comparison], next_cursor: null });
      }
      if (url.pathname === `/projects/${projectId}/comparisons/${comparisonId}` && !init?.method) {
        return response(comparison);
      }
      if (url.pathname === `/projects/${projectId}/comparisons/${comparisonId}` && init?.method === "PATCH") {
        const command = JSON.parse(String(init.body)) as Record<string, unknown>;
        updates.push(command);
        comparison = { ...comparison, ...command, comparison_revision: Number(comparison.comparison_revision) + 1 };
        return response(comparison);
      }
      throw new Error(`Unexpected request ${init?.method ?? "GET"} ${url.pathname}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithQuery(<ComparisonPage />, `/projects/${projectId}/compare/${comparisonId}`);

    fireEvent.click(await screen.findByRole("button", { name: "Show differences only" }));
    await waitFor(() => expect(updates).toHaveLength(1));
    expect(updates[0]).toMatchObject({
      expected_version: 1,
      expected_comparison_version: 1,
      display_mode: "differences",
    });
    expect(updates[0]).not.toHaveProperty("project_product_ids");
    expect(updates[0]).not.toHaveProperty("dimensions");

    fireEvent.change(await screen.findByDisplayValue("Saved vacuum comparison"), { target: { value: "Warranty shortlist" } });
    fireEvent.click(screen.getByRole("button", { name: "Save comparison definition" }));
    await waitFor(() => expect(updates).toHaveLength(2));
    expect(updates[1]).toMatchObject({
      expected_version: 1,
      expected_comparison_version: 2,
      title: "Warranty shortlist",
    });
    expect(updates[1]).not.toHaveProperty("project_product_ids");
    expect(updates[1]).not.toHaveProperty("dimensions");
  });
});
