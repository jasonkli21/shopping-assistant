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
  fireEvent.keyDown(window, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole("button", { name: "Inspect cited claim" })).toHaveFocus());
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
