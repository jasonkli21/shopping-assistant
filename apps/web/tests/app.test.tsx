import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MessageRead, ProductRead, Project, ProposalRead, Requirement } from "../src/api/client";
import { App } from "../src/app/App";

const PROJECT_ID = "6f16a208-307f-4dfc-8a2d-44aeb6df4d50";
const REQUIREMENT_ID = "a2b837ac-511a-4f86-9e76-2c988246c4e4";
const SECOND_REQUIREMENT_ID = "c2cf6497-9e70-41b6-844d-418320c3ea18";
const SECOND_PROJECT_ID = "d2cf6497-9e70-41b6-844d-418320c3ea18";
const timestamp = "2026-10-03T12:00:00Z";

function requirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: REQUIREMENT_ID,
    project_id: PROJECT_ID,
    kind: "must_have",
    label: "Handles pet hair",
    detail: null,
    attribute_key: null,
    operator: null,
    value: null,
    unit: null,
    position: 0,
    origin: "user",
    created_at: timestamp,
    updated_at: timestamp,
    ...overrides,
  };
}

function project(overrides: Partial<Project> = {}): Project {
  return {
    id: PROJECT_ID,
    title: "Apartment vacuum",
    goal: "Find a cordless vacuum for pet hair.",
    category: null,
    status: "active",
    budget_target: null,
    budget_maximum: null,
    budget_currency: null,
    notes: null,
    revision: 1,
    created_at: timestamp,
    updated_at: timestamp,
    requirements: [],
    ...overrides,
  };
}

function proposalMessage(proposal: ProposalRead, id = SECOND_REQUIREMENT_ID): MessageRead {
  return {
    id,
    conversation_id: "d2b837ac-511a-4f86-9e76-2c988246c4e5",
    project_id: PROJECT_ID,
    paired_message_id: null,
    ordinal: 2,
    role: "assistant",
    text: "I prepared a suggestion for your review.",
    status: "completed",
    request_key: null,
    snapshot_revision: 1,
    sequence: 1,
    error_code: null,
    clarification_questions: [],
    created_at: timestamp,
    completed_at: timestamp,
    proposal,
  };
}

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function renderApp(path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("catalog product detail", () => {
  it("shows variant provenance and paginates timestamped offers with safe outbound links", async () => {
    const productId = "302ae131-b98e-4fd0-81de-ce644192688f";
    const variantId = "396d0c5b-6732-4d62-a016-4a5e9f11e9b9";
    const productData: ProductRead = {
      id: productId,
      canonical_name: "Acme Clean 4",
      brand: "Acme",
      category: "vacuum",
      model_family: "AX-400",
      revision: 2,
      created_at: timestamp,
      updated_at: timestamp,
      variants: [{
        id: variantId,
        product_id: productId,
        display_name: "Pet kit",
        identity_attributes: {
          bundle: { value: "pet kit", origin: "source", observation_id: "obs-1", excerpt: "pet kit" },
        },
        category_attributes: {
          power: { value: 220, unit: "AW", origin: "manufacturer", excerpt: "220 AW" },
        },
        revision: 1,
        identifiers: [],
        offers: [],
      }],
    };
    const offers = [
      {
        id: "8d287f99-5f0c-4ec6-a8e3-ecfc14b2aed2",
        variant_id: variantId,
        observation_id: "d9ed7fd7-603e-419e-a213-57d3e82640a0",
        retailer_name: "Shop One",
        retailer_domain: "shop.example",
        url: "https://shop.example/item",
        amount: "319.00",
        currency: "USD",
        availability: "in_stock" as const,
        condition: "new" as const,
        observed_at: timestamp,
      },
      {
        id: "62e600a5-dfd4-4e0f-a781-cc56dc0bf359",
        variant_id: variantId,
        observation_id: "d9ed7fd7-603e-419e-a213-57d3e82640a0",
        retailer_name: "Unsafe listing",
        retailer_domain: null,
        url: "javascript:alert(1)",
        amount: null,
        currency: null,
        availability: "unknown" as const,
        condition: "unknown" as const,
        observed_at: timestamp,
      },
    ];
    let olderOffersRequested = false;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === `/products/${productId}`) return response(productData);
      if (url.pathname === `/products/${productId}/offers`) {
        if (url.searchParams.has("cursor")) {
          olderOffersRequested = true;
          return response({ items: [], next_cursor: null, catalog_version: 2 });
        }
        return response({ items: offers, next_cursor: "older-page", catalog_version: 2 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/products/${productId}`);

    expect(await screen.findByRole("heading", { name: "Acme Clean 4" })).toBeInTheDocument();
    expect(screen.getByText("Canonical product · Product revision 2")).toBeInTheDocument();
    expect(screen.getByText("pet kit")).toBeInTheDocument();
    expect(screen.getByText(/Observed on source page/)).toBeInTheDocument();
    expect(screen.getByText("220 AW")).toBeInTheDocument();
    expect(await screen.findByText("USD 319.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open retailer page/ })).toHaveAttribute("href", "https://shop.example/item");
    expect(screen.getByText("Retailer link unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load older offers" }));
    await waitFor(() => expect(olderOffersRequested).toBe(true));
  });
});

describe("project Home", () => {
  it("shows a helpful empty state and creates a project from the goal form", async () => {
    const created = project();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/projects?") && !init?.method) return response({ items: [], next_cursor: null });
      if (url.endsWith("/projects") && init?.method === "POST") return response(created, 201);
      if (url.endsWith(`/projects/${PROJECT_ID}`)) return response(created);
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    expect(await screen.findByRole("heading", { name: "Your first project starts here" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Apartment vacuum" } });
    fireEvent.change(screen.getByLabelText("What are you looking for?"), {
      target: { value: "Find a cordless vacuum for pet hair." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    const projectHeading = await screen.findByRole("heading", { name: "Apartment vacuum" });
    expect(projectHeading).toBeInTheDocument();
    expect(projectHeading).toHaveFocus();
    const createCall = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(createCall).toBeDefined();
    expect(JSON.parse(String(createCall?.[1]?.body))).toEqual({
      title: "Apartment vacuum",
      goal: "Find a cordless vacuum for pet hair.",
    });
  });

  it("keeps new-project entries after a server error and retries the recent list", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ items: [], next_cursor: null }, 503))
      .mockResolvedValueOnce(response({
        error: { code: "unavailable", message: "Project service is unavailable.", request_id: "req-1" },
      }, 503))
      .mockResolvedValueOnce(response({ items: [], next_cursor: null }));
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Desk lamp" } });
    fireEvent.change(screen.getByLabelText("What are you looking for?"), { target: { value: "Warm light" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    expect(await screen.findByText(/Your entries are still here/)).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveValue("Desk lamp");

    fireEvent.click(screen.getByRole("button", { name: "Retry loading projects" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "Your first project starts here" })).toBeInTheDocument());
  });

  it("announces a pending create and prevents duplicate submissions", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      void _init;
      if (String(input).includes("/projects?")) return Promise.resolve(response({ items: [], next_cursor: null }));
      return new Promise<ReturnType<typeof response>>(() => {});
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "Desk lamp" } });
    fireEvent.change(screen.getByLabelText("What are you looking for?"), { target: { value: "Warm light" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("button", { name: "Creating project…" })).toBeDisabled();
    fireEvent.submit(screen.getByRole("button", { name: "Creating project…" }).closest("form")!);
    expect(screen.getByRole("status")).toHaveTextContent("Saving your project");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });
});

describe("project Overview", () => {
  it("shows a loading state and can retry after a temporary load failure", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response({ error: { message: "Temporarily unavailable" } }, 503))
      .mockResolvedValueOnce(response(project()));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    expect(screen.getByRole("status")).toHaveTextContent("Loading project");
    fireEvent.click(await screen.findByRole("button", { name: "Retry loading project" }));
    const heading = await screen.findByRole("heading", { name: "Apartment vacuum" });
    expect(heading).toHaveFocus();
  });

  it("shows a distinct unavailable state for a missing or deleted project", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({
      error: { code: "not_found", message: "Project not found" },
    }, 404)));
    renderApp(`/projects/${PROJECT_ID}`);

    expect(await screen.findByRole("heading", { name: "This project can’t be opened." })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Return to projects" })).toHaveAttribute("href", "/");
  });

  it("saves project details as a revisioned patch", async () => {
    const initial = project();
    const updated = project({ title: "Quiet apartment vacuum", revision: 2 });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(initial);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && init?.method === "PATCH") return response(updated);
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    fireEvent.change(await screen.findByLabelText("Project name"), { target: { value: "Quiet apartment vacuum" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved revision 2");

    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body))).toMatchObject({
      expected_version: 1,
      title: "Quiet apartment vacuum",
    });
  });

  it("locks project fields during a delayed successful save", async () => {
    const initial = project();
    const saved = project({ title: "Quiet apartment vacuum", revision: 2 });
    const pendingResponse = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return Promise.resolve(response(initial));
      if (url.endsWith(`/projects/${PROJECT_ID}`) && init?.method === "PATCH") return pendingResponse.promise;
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const title = await screen.findByLabelText("Project name");
    fireEvent.change(title, { target: { value: saved.title } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));

    expect(title).toBeDisabled();
    expect(screen.getByLabelText("Goal")).toBeDisabled();
    pendingResponse.resolve(response(saved));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved revision 2");
    expect(screen.getByLabelText("Project name")).toHaveValue(saved.title);
  });

  it.each(["existing requirement", "new requirement"])(
    "blocks assistant send and apply while a %s draft is unsaved",
    async (draftKind) => {
      const existingRequirement = requirement();
      const initial = project({
        requirements: draftKind === "existing requirement" ? [existingRequirement] : [],
      });
      const proposal: ProposalRead = {
        id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
        project_id: PROJECT_ID,
        assistant_message_id: SECOND_REQUIREMENT_ID,
        base_revision: 1,
        schema_version: 1,
        operations: { project_updates: { category: "Vacuum" }, requirement_operations: [] },
        status: "pending",
        applied_revision: null,
        applied_at: null,
        applied_project: null,
        created_at: timestamp,
        updated_at: timestamp,
      };
      const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
        void _init;
        const url = String(input);
        if (url.endsWith(`/projects/${PROJECT_ID}`)) return response(initial);
        if (url.includes(`/projects/${PROJECT_ID}/messages?`)) {
          return response({ items: [proposalMessage(proposal)], next_cursor: null });
        }
        throw new Error(`Unexpected request: ${url}`);
      });
      vi.stubGlobal("fetch", fetchMock);
      renderApp(`/projects/${PROJECT_ID}`);

      await screen.findByRole("heading", { name: "Apartment vacuum" });
      fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
      expect(await screen.findByText("AI suggestion")).toBeInTheDocument();
      if (draftKind === "existing requirement") {
        fireEvent.change(screen.getByDisplayValue("Handles pet hair"), {
          target: { value: "Keeps the draft safe" },
        });
      } else {
        fireEvent.change(screen.getByPlaceholderText("Works well on pet hair"), {
          target: { value: "Keeps the draft safe" },
        });
      }

      expect(screen.getByRole("button", { name: "Apply suggestion" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
      expect(screen.getByDisplayValue("Keeps the draft safe")).toBeInTheDocument();
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
    },
  );

  it("locks manual project and requirement fields while a proposal is being applied", async () => {
    const initial = project();
    const updated = project({ category: "Vacuum", revision: 2 });
    const proposal: ProposalRead = {
      id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
      project_id: PROJECT_ID,
      assistant_message_id: SECOND_REQUIREMENT_ID,
      base_revision: 1,
      schema_version: 1,
      operations: { project_updates: { category: "Vacuum" }, requirement_operations: [] },
      status: "pending",
      applied_revision: null,
      applied_at: null,
      applied_project: null,
      created_at: timestamp,
      updated_at: timestamp,
    };
    const appliedProposal = {
      ...proposal,
      status: "applied" as const,
      applied_revision: 2,
      applied_at: timestamp,
      applied_project: updated,
    };
    const delayedApply = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) {
        return Promise.resolve(response(initial));
      }
      if (url.includes(`/projects/${PROJECT_ID}/messages?`) && !init?.method) {
        return Promise.resolve(response({ items: [proposalMessage(proposal)], next_cursor: null }));
      }
      if (url.endsWith(`/proposals/${proposal.id}/apply`)) return delayedApply.promise;
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    await screen.findByRole("heading", { name: "Apartment vacuum" });
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    expect(await screen.findByText("AI suggestion")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply suggestion" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));

    expect(screen.getByLabelText("Project name")).toBeDisabled();
    expect(screen.getByLabelText("Goal")).toBeDisabled();
    expect(screen.getByPlaceholderText("Works well on pet hair")).toBeDisabled();
    delayedApply.resolve(response({ proposal: appliedProposal, project: updated, replayed: false }));
    expect(await screen.findByText("Suggestion applied at revision 2.")).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveValue(updated.title);
  });

  it("cancels a project stream and clears its composer when cached navigation opens another project", async () => {
    const first = project();
    const second = project({ id: SECOND_PROJECT_ID, title: "Desk lamp", goal: "Find a warm desk lamp." });
    const generating: MessageRead = {
      id: "e2cf6497-9e70-41b6-844d-418320c3ea18",
      conversation_id: "d2b837ac-511a-4f86-9e76-2c988246c4e5",
      project_id: PROJECT_ID,
      paired_message_id: null,
      ordinal: 2,
      role: "assistant",
      text: "",
      status: "generating",
      request_key: null,
      snapshot_revision: 1,
      sequence: 0,
      error_code: null,
      clarification_questions: [],
      created_at: timestamp,
      completed_at: null,
    };
    const streamSignals: AbortSignal[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/projects?") && !init?.method) {
        return response({ items: [first, second], next_cursor: null });
      }
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(first);
      if (url.endsWith(`/projects/${SECOND_PROJECT_ID}`) && !init?.method) return response(second);
      if (url.includes(`/projects/${PROJECT_ID}/messages?`)) {
        return response({ items: [generating], next_cursor: null });
      }
      if (url.includes(`/projects/${SECOND_PROJECT_ID}/messages?`)) {
        return response({ items: [], next_cursor: null });
      }
      if (url.includes(`/projects/${PROJECT_ID}/messages/stream?`)) {
        if (init?.signal) streamSignals.push(init.signal);
        return new Promise<Response>(() => {});
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    await screen.findByRole("heading", { name: "Apartment vacuum" });
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));
    await screen.findByText(/Preparing suggestions|Response in progress/);
    await waitFor(() => expect(streamSignals).toHaveLength(1));
    fireEvent.change(screen.getByLabelText("Your shopping request"), {
      target: { value: "A private vacuum draft" },
    });

    fireEvent.click(screen.getByRole("link", { name: /All projects/ }));
    fireEvent.click(await screen.findByRole("link", { name: /Desk lamp/ }));
    await screen.findByRole("heading", { name: "Desk lamp" });
    fireEvent.click(screen.getByRole("button", { name: "Ask assistant" }));

    expect(await screen.findByText("Tell me what you’re shopping for.")).toBeInTheDocument();
    expect(screen.getByLabelText("Your shopping request")).toHaveValue("");
    expect(screen.queryByText(/Preparing suggestions|Response in progress/)).not.toBeInTheDocument();
    expect(streamSignals[0].aborted).toBe(true);
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });

  it("keeps a project draft after a failed save so the user can retry", async () => {
    const initial = project();
    const saved = project({ title: "Retry my project", revision: 2 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project service is unavailable." } }, 503))
      .mockResolvedValueOnce(response(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const title = await screen.findByLabelText("Project name");
    fireEvent.change(title, { target: { value: "Retry my project" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Project service is unavailable.");
    expect(screen.getByLabelText("Project name")).toHaveValue("Retry my project");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved revision 2");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2);
  });

  it("rebases a title edit without resending another tab's goal, notes, or budget", async () => {
    const initial = project({ budget_maximum: "400.00", budget_currency: "USD", notes: "Original notes" });
    const latest = project({
      goal: "Latest saved goal from another tab.",
      budget_maximum: "500.00",
      budget_currency: "USD",
      notes: "Latest notes from another tab.",
      revision: 2,
    });
    const saved = project({ ...latest, title: "My project title", revision: 3 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({
        error: { code: "revision_conflict", message: "Project changed", request_id: "req-conflict" },
      }, 409))
      .mockResolvedValueOnce(response(latest))
      .mockResolvedValueOnce(response(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    fireEvent.change(await screen.findByLabelText("Project name"), { target: { value: "My project title" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("heading", { name: "Reconcile your draft with revision 2" })).toBeInTheDocument();
    expect(screen.getByLabelText("Goal")).toHaveValue(latest.goal);
    expect(screen.getByLabelText(/^Notes/)).toHaveValue(latest.notes);
    expect(screen.getByLabelText(/^Maximum/)).toHaveValue("500.00");

    fireEvent.click(screen.getByRole("button", { name: "Apply reconciled draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("status");
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patches).toHaveLength(2);
    expect(JSON.parse(String(patches[1][1]?.body))).toEqual({
      expected_version: 2,
      title: "My project title",
    });
  });

  it("requires a choice when both tabs changed the same project field", async () => {
    const initial = project({ goal: "Original goal" });
    const latest = project({ goal: "Another tab's goal", revision: 2 });
    const saved = project({ goal: "My goal", revision: 3 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project changed" } }, 409))
      .mockResolvedValueOnce(response(latest))
      .mockResolvedValueOnce(response(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    fireEvent.change(await screen.findByLabelText("Goal"), { target: { value: "My goal" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("button", { name: "Keep my goal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply reconciled draft" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Keep my goal" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply reconciled draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2));
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(String(patches[1][1]?.body))).toEqual({ expected_version: 2, goal: "My goal" });
  });

  it("reconciles a requirement edit against another tab's non-overlapping change", async () => {
    const initialRequirement = requirement({ detail: "Original detail" });
    const latestRequirement = requirement({ detail: "Other tab's detail" });
    const initial = project({ requirements: [initialRequirement] });
    const latest = project({ requirements: [latestRequirement], revision: 2 });
    const savedRequirement = requirement({ label: "My requirement", detail: "Other tab's detail" });
    const saved = project({ requirements: [savedRequirement], revision: 3 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project changed" } }, 409))
      .mockResolvedValueOnce(response(latest))
      .mockResolvedValueOnce(response(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const label = await screen.findByDisplayValue("Handles pet hair");
    const row = label.closest("li");
    expect(row).not.toBeNull();
    fireEvent.change(label, { target: { value: "My requirement" } });
    fireEvent.click(within(row!).getByRole("button", { name: "Save requirement" }));

    expect(await screen.findByRole("heading", { name: "Reconcile your draft with revision 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Apply reconciled draft" }));
    expect(await within(row!).findByDisplayValue("Other tab's detail")).toBeInTheDocument();
    expect(within(row!).getByDisplayValue("My requirement")).toBeInTheDocument();
    fireEvent.click(within(row!).getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2));
    const requirementPatchCall = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")[1];
    expect(JSON.parse(String(requirementPatchCall[1]?.body))).toEqual({
      expected_version: 2,
      label: "My requirement",
    });
  });

  it("requires an explicit choice for an overlapping requirement edit", async () => {
    const initialRequirement = requirement();
    const latestRequirement = requirement({ label: "Latest requirement" });
    const initial = project({ requirements: [initialRequirement] });
    const latest = project({ requirements: [latestRequirement], revision: 2 });
    const saved = project({ requirements: [requirement({ label: "My requirement" })], revision: 3 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project changed" } }, 409))
      .mockResolvedValueOnce(response(latest))
      .mockResolvedValueOnce(response(saved));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const label = await screen.findByDisplayValue("Handles pet hair");
    const row = label.closest("li");
    expect(row).not.toBeNull();
    fireEvent.change(label, { target: { value: "My requirement" } });
    fireEvent.click(within(row!).getByRole("button", { name: "Save requirement" }));

    expect(await within(row!).findByRole("button", { name: "Keep my requirement" })).toBeInTheDocument();
    expect(within(row!).getByRole("button", { name: "Apply requirement draft" })).toBeDisabled();
    fireEvent.click(within(row!).getByRole("button", { name: "Keep my requirement" }));
    fireEvent.click(within(row!).getByRole("button", { name: "Apply requirement draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply reconciled draft" }));
    fireEvent.click(within(row!).getByRole("button", { name: "Save requirement" }));

    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2));
    const requirementPatchCall = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")[1];
    expect(JSON.parse(String(requirementPatchCall[1]?.body))).toEqual({
      expected_version: 2,
      label: "My requirement",
    });
  });

  it("keeps a dirty requirement visible when another tab deletes it", async () => {
    const initialRequirement = requirement();
    const initial = project({ requirements: [initialRequirement] });
    const latest = project({ revision: 2, requirements: [] });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project changed" } }, 409))
      .mockResolvedValueOnce(response(latest));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const requirementLabel = await screen.findByDisplayValue("Handles pet hair");
    const row = requirementLabel.closest("li");
    expect(row).not.toBeNull();
    fireEvent.change(requirementLabel, { target: { value: "Keep this draft" } });
    fireEvent.change(screen.getByLabelText("Project name"), { target: { value: "My title" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/This requirement was removed in the latest version/)).toBeInTheDocument();
    expect(within(row!).getByDisplayValue("Keep this draft")).toBeInTheDocument();
    expect(within(row!).getByRole("button", { name: "Save requirement" })).toBeDisabled();
    fireEvent.click(within(row!).getByRole("button", { name: "Discard this draft" }));
    await waitFor(() => expect(screen.queryByDisplayValue("Keep this draft")).not.toBeInTheDocument());
  });

  it("blocks another save after a second 409 cannot refresh the latest revision", async () => {
    const initial = project();
    const revision2 = project({ goal: "Revision two", revision: 2 });
    const revision3 = project({ goal: "Revision three", revision: 3 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({ error: { message: "Project changed" } }, 409))
      .mockResolvedValueOnce(response(revision2))
      .mockResolvedValueOnce(response({ error: { message: "Project changed again" } }, 409))
      .mockResolvedValueOnce(response({ error: { message: "Refresh failed" } }, 503))
      .mockResolvedValueOnce(response(revision3));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    fireEvent.change(await screen.findByLabelText("Project name"), { target: { value: "My title" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Apply reconciled draft" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/latest project version could not be loaded/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Delete project" })).toBeDisabled();
    expect(screen.getByLabelText("Project name")).toHaveValue("My title");
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Retry loading latest version" }));
    expect(await screen.findByRole("heading", { name: "Reconcile your draft with revision 3" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveValue("My title");
  });

  it("adds a requirement and reorders it through the revisioned API", async () => {
    const first = requirement();
    const second = requirement({ id: SECOND_REQUIREMENT_ID, label: "Easy to store", position: 1 });
    const initial = project({ requirements: [first, second] });
    const reordered = project({ requirements: [second, first], revision: 2 });
    const addedRequirement = requirement({
      id: "c92bc3ef-65bf-4d99-aa64-07dd8b303c10",
      label: "Quiet operation",
      position: 2,
    });
    const afterAdd = project({ requirements: [first, second, addedRequirement], revision: 2 });
    let detailReads = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) {
        detailReads += 1;
        return response(initial);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/requirements?expected_version=1`) && init?.method === "POST") {
        return response(afterAdd);
      }
      if (url.endsWith(`/requirements/${SECOND_REQUIREMENT_ID}`) && init?.method === "PATCH") {
        return response(reordered);
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}; detail reads ${detailReads}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    fireEvent.change(await screen.findByPlaceholderText("Works well on pet hair"), { target: { value: "Quiet operation" } });
    fireEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    expect(await screen.findByDisplayValue("Quiet operation")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Move Easy to store up" }));
    await waitFor(() => {
      const items = screen.getAllByRole("listitem");
      const requirementItems = items.filter((item) => within(item).queryByLabelText("Requirement"));
      expect(within(requirementItems[0]).getByDisplayValue("Easy to store")).toBeInTheDocument();
    });
    const mutationCalls = fetchMock.mock.calls.filter(([, init]) => ["POST", "PATCH"].includes(init?.method ?? ""));
    expect(mutationCalls).toHaveLength(2);
    expect(JSON.parse(String(mutationCalls[1][1]?.body))).toMatchObject({ expected_version: 2, position: 0 });
  });

  it("locks requirement drafts during delayed save and create requests", async () => {
    const initialRequirement = requirement();
    const initial = project({ requirements: [initialRequirement] });
    const updatedRequirement = requirement({ label: "My requirement" });
    const afterPatch = project({ requirements: [updatedRequirement], revision: 2 });
    const addedRequirement = requirement({
      id: SECOND_REQUIREMENT_ID,
      label: "Quiet operation",
      position: 1,
    });
    const afterCreate = project({ requirements: [updatedRequirement, addedRequirement], revision: 3 });
    const pendingPatch = deferred<ReturnType<typeof response>>();
    const pendingCreate = deferred<ReturnType<typeof response>>();
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return Promise.resolve(response(initial));
      if (url.endsWith(`/requirements/${REQUIREMENT_ID}`) && init?.method === "PATCH") return pendingPatch.promise;
      if (url.endsWith(`/projects/${PROJECT_ID}/requirements?expected_version=2`) && init?.method === "POST") {
        return pendingCreate.promise;
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const requirementLabel = await screen.findByDisplayValue(initialRequirement.label);
    const row = requirementLabel.closest("li")!;
    fireEvent.change(requirementLabel, { target: { value: updatedRequirement.label } });
    fireEvent.click(within(row).getByRole("button", { name: "Save requirement" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    expect(requirementLabel).toBeDisabled();
    pendingPatch.resolve(response(afterPatch));
    expect(await within(row).findByRole("status")).toHaveTextContent("Requirement saved");

    const newRequirementLabel = screen.getByPlaceholderText("Works well on pet hair");
    fireEvent.change(newRequirementLabel, { target: { value: addedRequirement.label } });
    fireEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(true));
    expect(newRequirementLabel).toBeDisabled();
    pendingCreate.resolve(response(afterCreate));
    await waitFor(() => expect(screen.getByPlaceholderText("Works well on pet hair")).toHaveValue(""));
  });

  it("confirms a delete before sending a tombstone request and returns home", async () => {
    const initial = project();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(initial);
      if (url.endsWith(`/projects/${PROJECT_ID}?expected_version=1`) && init?.method === "DELETE") {
        return response(undefined, 204);
      }
      if (url.includes("/projects?") && !init?.method) return response({ items: [], next_cursor: null });
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    renderApp(`/projects/${PROJECT_ID}`);

    await screen.findByRole("heading", { name: "Apartment vacuum" });
    fireEvent.click(screen.getByRole("button", { name: "Delete project" }));
    expect(await screen.findByRole("heading", { name: "Your first project starts here" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveFocus();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "DELETE")).toBe(true);
  });
});
