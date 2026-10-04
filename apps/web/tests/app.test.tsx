import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Project, Requirement } from "../src/api/client";
import { App } from "../src/app/App";

const PROJECT_ID = "6f16a208-307f-4dfc-8a2d-44aeb6df4d50";
const REQUIREMENT_ID = "a2b837ac-511a-4f86-9e76-2c988246c4e4";
const SECOND_REQUIREMENT_ID = "c2cf6497-9e70-41b6-844d-418320c3ea18";
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

function response(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
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

  it("preserves edits on a stale revision and waits for an explicit review", async () => {
    const initial = project();
    const latest = project({ goal: "Latest saved goal from another tab.", revision: 2 });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(initial))
      .mockResolvedValueOnce(response({
        error: {
          code: "revision_conflict",
          message: "Project was changed by another request.",
          details: { current_version: 2 },
          request_id: "req-conflict",
        },
      }, 409))
      .mockResolvedValueOnce(response(latest));
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/projects/${PROJECT_ID}`);

    const title = await screen.findByLabelText("Project name");
    fireEvent.change(title, { target: { value: "My unsaved edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("heading", { name: "Review the latest version before saving" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project name")).toHaveValue("My unsaved edit");
    expect(screen.getByText(/Latest saved goal from another tab/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "I reviewed this version" }));
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
    expect(screen.getByLabelText("Project name")).toHaveValue("My unsaved edit");
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
