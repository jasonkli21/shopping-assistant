import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Project, ResearchRunRead } from "../src/api/client";
import { App } from "../src/app/App";

const PROJECT_ID = "6f16a208-307f-4dfc-8a2d-44aeb6df4d50";
const RUN_ID = "8b3e7047-0e09-4bf4-b1fd-c63fc43cb711";
const timestamp = "2026-10-04T12:00:00Z";

function project(): Project {
  return {
    id: PROJECT_ID,
    title: "Apartment vacuum",
    goal: "Find a cordless vacuum for pet hair",
    category: "Vacuum",
    status: "active",
    budget_target: null,
    budget_maximum: "400.00",
    budget_currency: "USD",
    notes: null,
    revision: 3,
    created_at: timestamp,
    updated_at: timestamp,
    requirements: [
      {
        id: "45b15872-b9e8-40a2-8c3e-ec5ab8a8cab2",
        project_id: PROJECT_ID,
        kind: "must_have",
        label: "Works well on pet hair",
        detail: "Long-haired cat",
        attribute_key: null,
        operator: null,
        value: null,
        unit: null,
        position: 0,
        origin: "user",
        created_at: timestamp,
        updated_at: timestamp,
      },
    ],
  };
}

function run(overrides: Partial<ResearchRunRead> = {}): ResearchRunRead {
  return {
    id: RUN_ID,
    project_id: PROJECT_ID,
    objective: "Find cordless vacuums for pet hair",
    type: "discovery",
    status: "succeeded",
    snapshot_revision: 3,
    effective_budgets: {
      max_queries: 8,
      max_candidates: 20,
      max_results: 60,
      max_results_per_query: 10,
      max_attempts: 8,
      deadline_seconds: 60,
      max_concurrent: 1,
    },
    queries_planned: 1,
    queries_completed: 1,
    queries_failed: 0,
    attempts_used: 1,
    results_found: 1,
    candidates_found: 1,
    skipped_count: 0,
    summary: "Discovery completed.",
    error_code: null,
    queued_at: timestamp,
    started_at: timestamp,
    finished_at: timestamp,
    queries: [
      {
        id: "9b967a67-2aa9-4330-8e97-3f0b88adf8f8",
        ordinal: 0,
        text: "cordless vacuum pet hair under 400 USD",
        purpose: "Find products that match the saved requirements.",
        max_results: 10,
        state: "succeeded",
        results_count: 1,
        candidates_count: 1,
        error_code: null,
        created_at: timestamp,
        started_at: timestamp,
        completed_at: timestamp,
        attempts: [
          {
            id: "1e20cae6-9027-4a35-b966-e87c19df8c51",
            attempt_number: 1,
            provider: "fake",
            status: "succeeded",
            error_code: null,
            provider_request_id: null,
            results_count: 1,
            started_at: timestamp,
            finished_at: timestamp,
          },
        ],
      },
    ],
    ...overrides,
  };
}

const candidate = {
  id: "507711ee-8731-4f44-b9a5-3fc59905b1be",
  project_id: PROJECT_ID,
  research_run_id: RUN_ID,
  provisional_name: "Cordless vacuum product page",
  brand_clue: null,
  model_clue: null,
  category_clue: null,
  discovery_reason: "Found for query: cordless vacuum pet hair under 400 USD",
  indicative_price_text: null,
  observed_at: timestamp,
  search_results: [
    {
      search_result_id: "f8d73849-0009-420f-a4da-633a1b20ee5e",
      query_id: "9b967a67-2aa9-4330-8e97-3f0b88adf8f8",
      query_text: "cordless vacuum pet hair under 400 USD",
      purpose: "Find products that match the saved requirements.",
      title: "Cordless vacuum product page",
      url: "https://retailer.example/products/vacuum",
      snippet: "A listing snippet with a $399 mention. <script>should stay text</script>",
      result_rank: 1,
      received_at: timestamp,
    },
  ],
};

function response(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

function renderApp() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/discover`]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function discoveryFetch(
  runData: ResearchRunRead | null,
  candidates: unknown[] = [],
  post?: (body: unknown) => ReturnType<typeof response> | Promise<ReturnType<typeof response>>,
) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(project());
    if (url.includes(`/projects/${PROJECT_ID}/research?`)) {
      return response({ items: runData ? [runData] : [], next_cursor: null });
    }
    if (url.endsWith(`/projects/${PROJECT_ID}/research`) && init?.method === "POST") {
      const body = JSON.parse(String(init.body)) as unknown;
      return post ? post(body) : response({ run_id: RUN_ID, status: "queued", replayed: false }, 202);
    }
    if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}/cancel`)) {
      return response({ run: run({ status: "canceled", candidates_found: 0 }), replayed: false });
    }
    if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}`)) return response(runData ?? run());
    if (url.includes(`/projects/${PROJECT_ID}/candidates?`)) return response({ items: candidates, next_cursor: null });
    if (url.includes(`/projects/${PROJECT_ID}/products?`)) {
      return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
    }
    throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
  });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe("Discover", () => {
  it("shows saved requirements and renders only provisional search observations", async () => {
    const done = run();
    const fetchMock = discoveryFetch(done, [candidate]);
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    expect(await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" })).toBeInTheDocument();
    expect(screen.getByText("Works well on pet hair")).toBeInTheDocument();
    expect(screen.getByText("Up to 400.00 USD")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Cordless vacuum product page" })).toBeInTheDocument();
    expect(screen.getByText("Provisional · not yet matched")).toBeInTheDocument();
    expect(screen.getByText(/A listing snippet with a \$399 mention/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /script/ })).not.toBeInTheDocument();
    const sourceLink = screen.getByRole("link", { name: /Cordless vacuum product page/ });
    expect(sourceLink).toHaveAttribute("target", "_blank");
    expect(sourceLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Project revision 3/)).toBeInTheDocument();
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
  });

  it("creates a new variant within an existing product family with a reason", async () => {
    const saved: Record<string, unknown>[] = [];
    const variantChoice = {
      variant_id: "32941741-d069-4a20-8b8c-8b0cf6e450e8",
      product_id: "b857dc62-dddf-46ad-b9f4-d2bb998a36dd",
      canonical_name: "Acme Clean 4",
      brand: "Acme",
      category: "vacuum",
      model_family: "AX-400",
      variant_name: "Body only",
      identity_attributes: { bundle: { value: "body only", origin: "source" } },
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === `/projects/${PROJECT_ID}`) return response(project());
      if (url.pathname === `/projects/${PROJECT_ID}/research`) return response({ items: [run()], next_cursor: null });
      if (url.pathname === `/projects/${PROJECT_ID}/research/${RUN_ID}`) return response(run());
      if (url.pathname === `/projects/${PROJECT_ID}/candidates`) return response({ items: [candidate], next_cursor: null });
      if (url.pathname === `/projects/${PROJECT_ID}/products`) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      if (url.pathname === "/products") {
        return response({ items: [variantChoice], next_cursor: null, catalog_version: 1 });
      }
      if (url.pathname.endsWith("/correction") && init?.method === "POST") {
        saved.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return response({
          candidate_id: candidate.id,
          event_id: "de3eac0e-67e0-4ad1-9618-d9a6ddc4c319",
          status: "manual_linked",
          previous_project_product_id: null,
          selected_project_product_id: "d82867c8-59e1-442a-aa3b-13125843492a",
          catalog_version: 2,
          project_version: 4,
          reason: "This is the same family with a distinct kit.",
          replayed: false,
        });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    await screen.findByRole("heading", { name: "Cordless vacuum product page" });
    fireEvent.click(screen.getByRole("button", { name: "Assign or correct match" }));
    fireEvent.click(screen.getByLabelText("Create a new variant under an existing product"));
    fireEvent.change(await screen.findByLabelText("Product family"), {
      target: { value: variantChoice.product_id },
    });
    fireEvent.change(screen.getByLabelText("Variant name"), { target: { value: "Pet kit" } });
    fireEvent.change(screen.getByLabelText(/Known variant identity values/), {
      target: { value: '{"bundle":"pet kit"}' },
    });
    fireEvent.change(screen.getByLabelText("Why is this match correct?"), {
      target: { value: "This is the same model family with a distinct kit." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save manual correction" }));

    await screen.findByText("Your assignment was saved and can be reverted.");
    expect(saved).toHaveLength(1);
    expect(saved[0]?.new_variant).toEqual({
      product_id: variantChoice.product_id,
      display_name: "Pet kit",
      identity_attributes: { bundle: "pet kit" },
      category_attributes: [],
    });
    expect(saved[0]?.new_product).toBeUndefined();
  });

  it("submits explicit queries and keeps entries after a definitive busy rejection", async () => {
    let calls = 0;
    const sent: Record<string, unknown>[] = [];
    let acceptedRun: ResearchRunRead | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(project());
      if (url.includes(`/projects/${PROJECT_ID}/research?`)) return response({ items: acceptedRun ? [acceptedRun] : [] });
      if (url.endsWith(`/projects/${PROJECT_ID}/research`) && init?.method === "POST") {
        calls += 1;
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        sent.push(body);
        if (calls === 1) {
          return response({ error: { code: "research_active", message: "Another discovery is running." } }, 409);
        }
        acceptedRun = run();
        return response({ run_id: RUN_ID, status: "queued", replayed: false }, 202);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}`)) return response(acceptedRun ?? run());
      if (url.includes(`/projects/${PROJECT_ID}/candidates?`)) return response({ items: [candidate], next_cursor: null });
      if (url.includes(`/projects/${PROJECT_ID}/products?`)) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    fireEvent.click(screen.getByLabelText("Enter exact search queries myself"));
    fireEvent.change(screen.getByLabelText(/What would you like to find/), {
      target: { value: "Find a quiet cordless vacuum" },
    });
    fireEvent.change(screen.getByLabelText(/Search queries/), {
      target: { value: "cordless vacuum pet hair under $400 USD\nquiet apartment vacuum" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Another discovery is running");
    expect(screen.getByLabelText(/Search queries/)).toHaveValue(
      "cordless vacuum pet hair under $400 USD\nquiet apartment vacuum",
    );
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));

    await screen.findByRole("heading", { name: "Cordless vacuum product page" });
    expect(sent[0].manual_queries).toEqual([
      "cordless vacuum pet hair under $400 USD",
      "quiet apartment vacuum",
    ]);
    expect(sent[1].request_key).not.toBe(sent[0].request_key);
  });

  it("prevents duplicate submits while the command acknowledgement is delayed", async () => {
    const pending = deferred<ReturnType<typeof response>>();
    const post = vi.fn((command: unknown) => {
      void command;
      return pending.promise;
    });
    vi.stubGlobal("fetch", discoveryFetch(null, [], post));
    renderApp();
    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    fireEvent.change(screen.getByLabelText(/What would you like to find/), {
      target: { value: "Find a canister vacuum" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));
    expect(await screen.findByRole("button", { name: "Checking request…" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Checking request…" }));
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0]?.[0]).toMatchObject({
      expected_version: 3,
      request_key: expect.any(String),
    });
    pending.resolve(response({ run_id: RUN_ID, status: "queued", replayed: false }, 202));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Starting discovery…" })).not.toBeInTheDocument());
  });

  it("offers exact request replay after reload when the previous acknowledgement was lost", async () => {
    const saved = {
      requestKey: "lost-ack-request-0001",
      command: {
        objective: "Find a vacuum and preserve my query",
        type: "discovery",
        request_key: "lost-ack-request-0001",
        expected_version: 3,
        manual_queries: ["exact query from previous page"],
      },
    };
    window.sessionStorage.setItem(
      `shopping-assistant:discovery-command:${PROJECT_ID}`,
      JSON.stringify(saved),
    );
    const post = vi.fn((body: unknown) => {
      expect(body).toEqual(saved.command);
      return response({ run_id: RUN_ID, status: "queued", replayed: true }, 202);
    });
    vi.stubGlobal("fetch", discoveryFetch(run(), [candidate], post));
    renderApp();
    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    expect(screen.getByLabelText(/What would you like to find/)).toHaveValue(saved.command.objective);
    expect(screen.getByLabelText("Enter exact search queries myself")).toBeChecked();
    expect(screen.getByLabelText(/Search queries/)).toHaveValue("exact query from previous page");
    fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(window.sessionStorage.getItem(
      `shopping-assistant:discovery-command:${PROJECT_ID}`,
    )).toBeNull());
  });

  it("refreshes a stale project revision and lets the preserved form start with a new key", async () => {
    const sent: Record<string, unknown>[] = [];
    let projectLoads = 0;
    let accepted: ResearchRunRead | null = null;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) {
        projectLoads += 1;
        return response({ ...project(), revision: projectLoads === 1 ? 3 : 4 });
      }
      if (url.includes(`/projects/${PROJECT_ID}/research?`)) {
        return response({ items: accepted ? [accepted] : [], next_cursor: null });
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/research`) && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as Record<string, unknown>;
        sent.push(body);
        if (sent.length === 1) {
          return response({
            error: { code: "revision_conflict", message: "The project changed before discovery started." },
          }, 409);
        }
        accepted = run({ status: "running", candidates_found: 0, results_found: 0 });
        return response({ run_id: RUN_ID, status: "queued", replayed: false }, 202);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}`)) return response(accepted ?? run());
      if (url.includes(`/projects/${PROJECT_ID}/candidates?`)) return response({ items: [], next_cursor: null });
      if (url.includes(`/projects/${PROJECT_ID}/products?`)) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    fireEvent.change(screen.getByLabelText(/What would you like to find/), {
      target: { value: "Find a quiet vacuum" },
    });
    fireEvent.click(screen.getByLabelText("Enter exact search queries myself"));
    fireEvent.change(screen.getByLabelText(/Search queries/), {
      target: { value: "quiet vacuum query" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("latest revision is loaded");
    expect(projectLoads).toBe(2);
    expect(screen.getByLabelText(/What would you like to find/)).toHaveValue("Find a quiet vacuum");
    expect(screen.getByLabelText(/Search queries/)).toHaveValue("quiet vacuum query");
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[0]?.expected_version).toBe(3);
    expect(sent[1]?.expected_version).toBe(4);
    expect(sent[1]?.request_key).not.toBe(sent[0]?.request_key);
  });

  it("keeps the same key after an unclassified service-unavailable response", async () => {
    const sent: Record<string, unknown>[] = [];
    let attempt = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`) && !init?.method) return response(project());
      if (url.includes(`/projects/${PROJECT_ID}/research?`)) return response({ items: [], next_cursor: null });
      if (url.endsWith(`/projects/${PROJECT_ID}/research`) && init?.method === "POST") {
        sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        attempt += 1;
        return attempt === 1
          ? response({ error: { code: "unexpected_service_error", message: "Unavailable." } }, 503)
          : response({ run_id: RUN_ID, status: "queued", replayed: true }, 202);
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}`)) return response(run({ status: "running" }));
      if (url.includes(`/projects/${PROJECT_ID}/candidates?`)) return response({ items: [], next_cursor: null });
      if (url.includes(`/projects/${PROJECT_ID}/products?`)) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    fireEvent.click(screen.getByRole("button", { name: "Start discovery" }));
    expect(await screen.findByRole("button", { name: "Retry the same request" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    await waitFor(() => expect(sent).toHaveLength(2));
    expect(sent[1]).toEqual(sent[0]);
  });

  it("ignores malformed saved command storage", async () => {
    window.sessionStorage.setItem(
      `shopping-assistant:discovery-command:${PROJECT_ID}`,
      JSON.stringify({ requestKey: "bad-key", command: { objective: 42 } }),
    );
    vi.stubGlobal("fetch", discoveryFetch(null));
    renderApp();
    await screen.findByRole("heading", { name: "Explore options for Apartment vacuum" });
    expect(screen.queryByRole("button", { name: "Retry the same request" })).not.toBeInTheDocument();
    expect(screen.getByLabelText(/What would you like to find/)).toHaveValue(project().goal);
    expect(window.sessionStorage.getItem(`shopping-assistant:discovery-command:${PROJECT_ID}`)).toBeNull();
  });

  it("refreshes the selected run candidates as soon as terminal results arrive", async () => {
    vi.useFakeTimers();
    const running = run({
      status: "running",
      finished_at: null,
      queries_completed: 0,
      candidates_found: 0,
      results_found: 0,
    });
    const complete = run({
      status: "succeeded",
      candidates_found: 1,
      results_found: 1,
      summary: "Discovery completed.",
    });
    let details = 0;
    let candidateFetches = 0;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith(`/projects/${PROJECT_ID}`)) return response(project());
      if (url.includes(`/projects/${PROJECT_ID}/research?`)) {
        return response({ items: [running], next_cursor: null });
      }
      if (url.endsWith(`/projects/${PROJECT_ID}/research/${RUN_ID}`)) {
        details += 1;
        return response(details === 1 ? running : complete);
      }
      if (url.includes(`/projects/${PROJECT_ID}/candidates?`)) {
        candidateFetches += 1;
        return response({ items: details > 1 ? [candidate] : [], next_cursor: null });
      }
      if (url.includes(`/projects/${PROJECT_ID}/products?`)) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      throw new Error(`Unexpected request: ${url}`);
    }));
    renderApp();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(screen.getByText("Search is in progress.")).toBeInTheDocument();
    const initialFetches = candidateFetches;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1301);
    });
    expect(screen.getByRole("heading", { name: "Cordless vacuum product page" })).toBeInTheDocument();
    const terminalFetches = candidateFetches;
    expect(terminalFetches).toBeGreaterThan(initialFetches);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(candidateFetches).toBe(terminalFetches);
    vi.useRealTimers();
  });

  it("loads candidates for an older selected run and pages beyond the first candidate page", async () => {
    const latestId = "ad9777ac-92f2-4c5b-940f-c54f4aafc044";
    const olderId = "09272aa4-1e46-48d0-a3a4-7b28c76c6712";
    const latest = run({ id: latestId, objective: "Latest vacuum search" });
    const older = run({ id: olderId, objective: "Older saved vacuum search" });
    const olderCandidate = { ...candidate, id: "older-candidate", research_run_id: olderId, provisional_name: "Older candidate" };
    const latestCandidates = Array.from({ length: 21 }, (_, index) => ({
      ...candidate,
      id: `latest-candidate-${index}`,
      research_run_id: latestId,
      provisional_name: `Latest candidate ${index + 1}`,
    }));
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input), "http://localhost");
      if (url.pathname === `/projects/${PROJECT_ID}`) return response(project());
      if (url.pathname === `/projects/${PROJECT_ID}/research`) {
        return url.searchParams.has("cursor")
          ? response({ items: [older], next_cursor: null })
          : response({ items: [latest], next_cursor: "older-runs" });
      }
      if (url.pathname === `/projects/${PROJECT_ID}/research/${latestId}`) return response(latest);
      if (url.pathname === `/projects/${PROJECT_ID}/research/${olderId}`) return response(older);
      if (url.pathname === `/projects/${PROJECT_ID}/candidates`) {
        const selected = url.searchParams.get("run_id");
        if (selected === olderId) return response({ items: [olderCandidate], next_cursor: null });
        const cursor = url.searchParams.get("cursor");
        return cursor
          ? response({ items: latestCandidates.slice(20), next_cursor: null })
          : response({ items: latestCandidates.slice(0, 20), next_cursor: "latest-more" });
      }
      if (url.pathname === `/projects/${PROJECT_ID}/products`) {
        return response({ items: [], next_cursor: null, catalog_version: 1, project_version: 3 });
      }
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    expect(await screen.findByRole("heading", { name: "Latest candidate 1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more candidates" }));
    expect(await screen.findByRole("heading", { name: "Latest candidate 21" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load older runs" }));
    const olderRun = await screen.findByRole("button", { name: /Older saved vacuum search/ });
    fireEvent.click(olderRun);
    expect(await screen.findByRole("heading", { name: "Older candidate" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([input]) => {
      const url = new URL(String(input), "http://localhost");
      return url.pathname.endsWith("/candidates") && url.searchParams.get("run_id") === olderId;
    })).toBe(true);
  });

  it("shows an empty result message and cancels a running run", async () => {
    const running = run({
      status: "running",
      finished_at: null,
      queries_completed: 0,
      candidates_found: 0,
      results_found: 0,
      queries: [
        {
          ...run().queries![0]!,
          state: "running",
          completed_at: null,
          attempts: [{ ...run().queries![0]!.attempts[0]!, status: "running", finished_at: null }],
        },
      ],
    });
    vi.stubGlobal("fetch", discoveryFetch(running));
    renderApp();
    expect(await screen.findByRole("button", { name: "Cancel discovery" })).toBeInTheDocument();
    expect(await screen.findByText("Search is in progress.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel discovery" }));
    await waitFor(() => expect(screen.getByText("canceled", { selector: ".run-status" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Cancel discovery" })).not.toBeInTheDocument();
  });

  it("explains successful empty searches and keeps run history selectable", async () => {
    const noResults = run({ candidates_found: 0, results_found: 0, summary: "No candidates were found." });
    vi.stubGlobal("fetch", discoveryFetch(noResults));
    renderApp();
    expect(await screen.findByRole("heading", { name: "No candidates found for this run." })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Find cordless vacuums.*0 candidates/ })).toBeInTheDocument();
  });
});
