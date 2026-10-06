import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ProductResearch } from "../src/features/products/ProductResearch";

const projectId = "11111111-1111-4111-8111-111111111111";
const productId = "22222222-2222-4222-8222-222222222222";
const claimId = "33333333-3333-4333-8333-333333333333";
const snapshotId = "44444444-4444-4444-8444-444444444444";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("opens the cited claim, preserves stale context, and closes with Escape", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    let body: unknown;
    if (url.pathname === `/projects/${projectId}`) body = { id: projectId, revision: 2, goal: "Runtime" };
    else if (url.pathname === `/projects/${projectId}/research`) body = { items: [], next_cursor: null };
    else if (url.pathname === `/projects/${projectId}/products/${productId}/research`) body = {
      project_product_id: productId,
      state: "researched",
      assessments: [{ id: "a", research_run_id: "r", project_product_id: productId, project_revision: 1, product_revision: 1, variant_revision: 1, generated_at: "2026-10-04T12:00:00Z", context_stale: true, summary: "Saved conclusion", uncertainties: [], conclusions: [{ requirement_label: "At least 40 minutes", status: "supports", rationale: "Cited source value meets the saved requirement.", claim_ids: [claimId] }] }],
      claims: [{ id: claimId, attribute_key: "runtime", assertion_text: "60 minutes in normal mode", evidence_category: "independent_measurement", qualifiers: { mode: "normal" }, source_id: "s", snapshot_id: snapshotId, source_title: "Independent test", source_url: "https://example.com/test", published_at: null, retrieved_at: "2026-10-04T12:00:00Z", freshness: "unknown" }],
      sources: [],
    };
    else if (url.pathname === `/projects/${projectId}/claims/${claimId}`) body = {
      id: claimId, attribute_key: "runtime", assertion_text: "60 minutes in normal mode", evidence_category: "independent_measurement", qualifiers: { mode: "normal" }, source_id: "s", snapshot_id: snapshotId, source_title: "Independent test", source_url: "https://example.com/test", published_at: null, retrieved_at: "2026-10-04T12:00:00Z", freshness: "unknown", normalized_value: 60, evidence_excerpt: "60 minutes in normal mode", locator: { start: 10, end: 35 }, content_hash: "hash", validation_warnings: [], relations: [],
    };
    else throw Error(`Unexpected request ${url.pathname}`);
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  expect(await screen.findByText(/Project requirements or product identity changed/)).toBeInTheDocument();
  const citationButton = screen.getByRole("button", { name: "Inspect cited claim" });
  citationButton.focus();
  fireEvent.click(citationButton);
  const dialog = await screen.findByRole("dialog", { name: "Evidence inspection" });
  await waitFor(() => expect(dialog).toHaveTextContent("60 minutes in normal mode"));
  expect(dialog).toHaveTextContent("Publication date unknown");
  let inertBackground: HTMLElement | null = citationButton.parentElement;
  while (inertBackground && !inertBackground.inert) inertBackground = inertBackground.parentElement;
  expect(inertBackground).not.toBeNull();
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole("button", { name: "Inspect cited claim" })).toHaveFocus());
  expect(inertBackground?.inert).not.toBe(true);
});

it("shows blocked attempts and opens the retained source excerpt", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    let body: unknown;
    if (url.pathname === `/projects/${projectId}`) body = { id: projectId, revision: 1, goal: "Runtime" };
    else if (url.pathname === `/projects/${projectId}/research`) body = { items: [], next_cursor: null };
    else if (url.pathname === `/projects/${projectId}/products/${productId}/research`) body = {
      project_product_id: productId, state: "partial", assessments: [], claims: [],
      sources: [
        { id: "attempt-1", snapshot_id: snapshotId, source_id: "source-1", requested_url: "https://example.com/test", final_url: "https://example.com/test", title: "Measured review", publisher: "example.com", classification: "independent_measurement", status: "retrieved", reason: null, retrieved_at: "2026-10-04T12:00:00Z", published_at: null, freshness: "unknown", bytes_read: 100 },
        { id: "attempt-2", snapshot_id: null, source_id: "source-2", requested_url: "https://blocked.example/test", final_url: "https://blocked.example/test", title: "Blocked review", publisher: "blocked.example", classification: "unknown", status: "blocked", reason: "blocked_address", retrieved_at: "2026-10-04T12:00:00Z", published_at: null, freshness: "unknown", bytes_read: null },
      ],
    };
    else if (url.pathname === `/projects/${projectId}/sources/${snapshotId}`) body = {
      id: snapshotId, source_id: "source-1", title: "Measured review", final_url: "https://example.com/test", classification: "independent_measurement", content_hash: "hash", published_at: null, retrieved_at: "2026-10-04T12:00:00Z", excerpt: "AX-4 HEPA was tested for runtime.", claims: [],
    };
    else throw Error(`Unexpected request ${url.pathname}`);
    return { ok: true, status: 200, json: async () => body };
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  expect(await screen.findByText(/Partial research/)).toBeInTheDocument();
  expect(screen.getByText(/blocked_address/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Inspect source excerpt" }));
  const dialog = await screen.findByRole("dialog", { name: "Evidence inspection" });
  await waitFor(() => expect(dialog).toHaveTextContent("AX-4 HEPA was tested for runtime."));
  expect(dialog).toHaveTextContent("Publication date unknown");
  fireEvent.click(screen.getByRole("button", { name: "Close evidence" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("pages assessment history and loads evidence from the selected run", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) return {
      ok: true, status: 200, json: async () => ({ id: projectId, revision: 1, goal: "Runtime" }),
    };
    if (url.pathname !== `/projects/${projectId}/products/${productId}/research`) throw Error(`Unexpected request ${url.pathname}`);
    const offset = Number(url.searchParams.get("assessment_offset"));
    const selectedRun = url.searchParams.get("research_run_id");
    return { ok: true, status: 200, json: async () => ({
      project_product_id: productId, latest_run_id: null, latest_run_status: null,
      state: "researched", has_more_assessments: offset === 0,
      assessments: [{ id: offset ? "old" : "new", research_run_id: offset ? "old-run" : "new-run", project_product_id: productId, project_revision: 1, product_revision: 1, variant_revision: 1, generated_at: "2026-10-04T12:00:00Z", context_stale: false, summary: "Saved", conclusions: [], uncertainties: [] }],
      claims: selectedRun === "old-run" ? [{ id: claimId, attribute_key: "runtime", assertion_text: "Old cited claim", evidence_category: "independent_measurement", qualifiers: {}, source_id: "s", snapshot_id: snapshotId, source_title: "Test", source_url: "https://example.com/test", published_at: null, retrieved_at: "2026-10-04T12:00:00Z", freshness: "unknown" }] : [],
      sources: [],
    }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Older assessments" }));
  await screen.findByRole("button", { name: "Newer assessments" });
  fireEvent.change(screen.getByLabelText("Assessment history"), { target: { value: "0" } });
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input)).searchParams.get("research_run_id") === "old-run")).toBe(true));
  expect(await screen.findByText(/Old cited claim/)).toBeInTheDocument();
});

it("pages claims and source attempts beyond the first evidence page", async () => {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) return {
      ok: true, status: 200, json: async () => ({ id: projectId, revision: 1, goal: "Runtime" }),
    };
    if (url.pathname !== `/projects/${projectId}/products/${productId}/research`) throw Error(`Unexpected request ${url.pathname}`);
    const claimOffset = Number(url.searchParams.get("claim_offset"));
    const sourceOffset = Number(url.searchParams.get("source_offset"));
    const stamp = "2026-10-04T12:00:00Z";
    return { ok: true, status: 200, json: async () => ({
      project_product_id: productId,
      latest_run_id: null,
      latest_run_status: null,
      state: "researched",
      assessments: [],
      has_more_assessments: false,
      has_more_claims: claimOffset === 0,
      has_more_sources: sourceOffset === 0,
      claims: [{
        id: claimOffset ? "older-claim" : "newer-claim",
        attribute_key: "runtime",
        assertion_text: claimOffset ? "Older cited runtime" : "Newer cited runtime",
        evidence_category: "independent_measurement",
        qualifiers: {},
        source_id: "s",
        snapshot_id: snapshotId,
        source_title: "Test source",
        source_url: "https://example.com/test",
        published_at: null,
        retrieved_at: stamp,
        freshness: "unknown",
      }],
      sources: [{
        id: sourceOffset ? "older-attempt" : "newer-attempt",
        snapshot_id: snapshotId,
        source_id: "s",
        requested_url: "https://example.com/test",
        final_url: "https://example.com/test",
        title: sourceOffset ? "Older source attempt" : "Newer source attempt",
        publisher: "example.com",
        classification: "independent_measurement",
        classification_basis: "Measured content",
        status: "retrieved",
        reason: null,
        retrieved_at: stamp,
        published_at: null,
        freshness: "unknown",
        bytes_read: 100,
      }],
    }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  expect(await screen.findByText(/Newer cited runtime/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Older claims" }));
  expect(await screen.findByText(/Older cited runtime/)).toBeInTheDocument();
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input)).searchParams.get("claim_offset") === "20")).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "Older source attempts" }));
  expect(await screen.findByText(/Older source attempt/)).toBeInTheDocument();
  await waitFor(() => expect(fetchMock.mock.calls.some(([input]) => new URL(String(input)).searchParams.get("source_offset") === "20")).toBe(true));
});

it("refreshes selected-product evidence after the latest run becomes terminal", async () => {
  let evidenceReads = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) return {
      ok: true, status: 200, json: async () => ({ id: projectId, revision: 1, goal: "Runtime" }),
    };
    if (url.pathname === `/projects/${projectId}/products/${productId}/research`) {
      evidenceReads += 1;
      const terminal = evidenceReads > 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          project_product_id: productId,
          latest_run_id: "run-1",
          latest_run_status: terminal ? "succeeded" : "running",
          state: terminal ? "researched" : "partial",
          assessments: [],
          has_more_assessments: false,
          claims: [],
          sources: [],
        }),
      };
    }
    if (url.pathname === `/projects/${projectId}/research/run-1`) return {
      ok: true,
      status: 200,
      json: async () => ({
        id: "run-1", status: "succeeded", summary: "The selected variant research completed.",
        targets: [], stages: [],
      }),
    };
    throw Error(`Unexpected request ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  expect(await screen.findByText(/Research running/)).toBeInTheDocument();
  expect(screen.queryByText(/Partial research:/)).not.toBeInTheDocument();
  await waitFor(() => expect(evidenceReads).toBeGreaterThan(1));
  expect(await screen.findByText(/Latest research completed: The selected variant research completed/)).toBeInTheDocument();
});

it("replays the exact saved command after an uncertain acknowledgement", async () => {
  const sent: Array<Record<string, unknown>> = [];
  let posts = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) return {
      ok: true, status: 200, json: async () => ({ id: projectId, revision: 3, goal: "Runtime" }),
    };
    if (url.pathname === `/projects/${projectId}/products/${productId}/research`) return {
      ok: true, status: 200, json: async () => ({
        project_product_id: productId, latest_run_id: null, latest_run_status: null,
        state: "no_research", assessments: [], has_more_assessments: false, claims: [], sources: [],
      }),
    };
    if (url.pathname === `/projects/${projectId}/research` && init?.method === "POST") {
      sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      posts += 1;
      if (posts === 1) throw new TypeError("connection reset after server accepted the command");
      return { ok: true, status: 202, json: async () => ({ run_id: "run-1", status: "queued", replayed: true }) };
    }
    throw Error(`Unexpected request ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  const start = await screen.findByRole("button", { name: "Research this variant" });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  const retry = await screen.findByRole("button", { name: "Retry research request" });
  fireEvent.click(retry);
  await waitFor(() => expect(posts).toBe(2));
  expect(sent[1]).toEqual(sent[0]);
  expect(sent[1].request_key).toBe(sent[0].request_key);
});

it("refreshes a known conflict and creates a new command key", async () => {
  const sent: Array<Record<string, unknown>> = [];
  let projectReads = 0;
  let posts = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) {
      projectReads += 1;
      return { ok: true, status: 200, json: async () => ({ id: projectId, revision: projectReads >= 3 ? 4 : 3, goal: "Runtime" }) };
    }
    if (url.pathname === `/projects/${projectId}/products/${productId}/research`) return {
      ok: true, status: 200, json: async () => ({
        project_product_id: productId, latest_run_id: null, latest_run_status: null,
        state: "no_research", assessments: [], has_more_assessments: false, claims: [], sources: [],
      }),
    };
    if (url.pathname === `/projects/${projectId}/research` && init?.method === "POST") {
      sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
      posts += 1;
      return posts === 1
        ? { ok: false, status: 409, json: async () => ({ error: { code: "revision_conflict", message: "Project changed" } }) }
        : { ok: true, status: 202, json: async () => ({ run_id: "run-2", status: "queued", replayed: false }) };
    }
    throw Error(`Unexpected request ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);
  const start = await screen.findByRole("button", { name: "Research this variant" });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  expect(await screen.findByRole("alert")).toHaveTextContent("project changed");
  fireEvent.click(screen.getByRole("button", { name: "Research this variant" }));
  await waitFor(() => expect(posts).toBe(2));
  expect(sent[0].expected_version).toBe(3);
  expect(sent[1].request_key).not.toBe(sent[0].request_key);
  expect(sent[1].expected_version).toBe(4);
});

it("replays an uncertain product retry with the original run and revision after a refresh", async () => {
  const sent: Array<{ path: string; body: Record<string, unknown> }> = [];
  let posts = 0;
  let projectReads = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input));
    if (url.pathname === `/projects/${projectId}`) {
      projectReads += 1;
      return { ok: true, status: 200, json: async () => ({ id: projectId, revision: projectReads > 1 ? 9 : 3, goal: "Runtime" }) };
    }
    if (url.pathname === `/projects/${projectId}/products/${productId}/research`) return {
      ok: true, status: 200, json: async () => ({
        project_product_id: productId, latest_run_id: "source-run", latest_run_status: "partial",
        state: "partial", assessments: [], has_more_assessments: false, claims: [], sources: [],
      }),
    };
    if (url.pathname === `/projects/${projectId}/research/source-run`) return {
      ok: true, status: 200, json: async () => ({
        id: "source-run", status: "partial", summary: "Some source work did not finish.",
        targets: [], stages: [], jobs: [], queries: [],
      }),
    };
    if (url.pathname === `/projects/${projectId}/research/source-run/retry` && init?.method === "POST") {
      sent.push({ path: url.pathname, body: JSON.parse(String(init.body)) as Record<string, unknown> });
      posts += 1;
      if (posts === 1) throw new TypeError("connection reset after retry acceptance");
      return { ok: true, status: 202, json: async () => ({ run_id: "retry-run", status: "queued", replayed: true }) };
    }
    throw Error(`Unexpected request ${url.pathname}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ProductResearch projectId={projectId} projectProductId={productId} /></QueryClientProvider>);

  fireEvent.click(await screen.findByRole("button", { name: "Retry incomplete research" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("connection reset after retry acceptance");
  await waitFor(() => expect(projectReads).toBeGreaterThan(1));
  fireEvent.click(screen.getByRole("button", { name: "Retry incomplete research" }));
  await waitFor(() => expect(posts).toBe(2));

  expect(sent[0].path).toBe(sent[1].path);
  expect(sent[1].body).toEqual(sent[0].body);
  expect(sent[1].body.expected_version).toBe(3);
  expect(sent[1].body.request_key).toBe(sent[0].body.request_key);
});
