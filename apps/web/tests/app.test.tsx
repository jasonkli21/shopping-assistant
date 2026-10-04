import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../src/app/App";

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the scaffold and calls the API health path", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    expect(screen.getByText(/Research products/i)).toBeInTheDocument();
    expect(await screen.findByText("API status: ok")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("http://localhost:8000/health");
  });

  it("shows loading while the request is pending", () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    renderApp();
    expect(screen.getByRole("status")).toHaveTextContent("Checking API connection");
  });

  it("recovers from an unavailable API with a retry", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce({ ok: false, status: 503 })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "ok" }) }));
    renderApp();
    expect(await screen.findByText(/API unavailable/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry connection" }));
    expect(await screen.findByText("API status: ok")).toBeInTheDocument();
  });
});
