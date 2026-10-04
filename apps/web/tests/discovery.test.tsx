import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
      return response({ items: runData ? [runData] : [] });
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
    throw new Error(`Unexpected request: ${init?.method ?? "GET"} ${url}`);
  });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
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
    expect(screen.getByText("Not normalized or researched")).toBeInTheDocument();
    expect(screen.getByText(/A listing snippet with a \$399 mention/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /script/ })).not.toBeInTheDocument();
    const sourceLink = screen.getByRole("link", { name: /Cordless vacuum product page/ });
    expect(sourceLink).toHaveAttribute("target", "_blank");
    expect(sourceLink).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Project revision 3/)).toBeInTheDocument();
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
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
    window.localStorage.setItem(
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
    fireEvent.click(screen.getByRole("button", { name: "Retry the same request" }));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(window.localStorage.getItem(
      `shopping-assistant:discovery-command:${PROJECT_ID}`,
    )).toBeNull());
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
