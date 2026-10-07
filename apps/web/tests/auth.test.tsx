import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthGate } from "../src/auth/AuthGate";
import { projectsApi } from "../src/api/client";

const mocks = vi.hoisted(() => ({
  auth: {
    currentUser: null as { getIdToken: () => Promise<string> } | null,
  },
  onAuthStateChanged: vi.fn(),
  signInWithEmailAndPassword: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock("../src/auth/firebase", () => ({ firebaseAuth: mocks.auth }));
vi.mock("firebase/auth", () => ({
  onAuthStateChanged: mocks.onAuthStateChanged,
  signInWithEmailAndPassword: mocks.signInWithEmailAndPassword,
  signOut: mocks.signOut,
}));

let authStateChanged: ((user: { uid: string } | null) => void) | undefined;

function renderAuthGate(queryClient = new QueryClient()) {
  render(
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <div>Private shopping data</div>
      </AuthGate>
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  mocks.auth.currentUser = null;
  authStateChanged = undefined;
  mocks.onAuthStateChanged.mockImplementation((_auth, callback) => {
    authStateChanged = callback;
    return vi.fn();
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.clearAllMocks();
});

describe("Firebase account boundary", () => {
  it("clears cached private state when the observed account changes and signs out", async () => {
    const queryClient = new QueryClient();
    const clear = vi.spyOn(queryClient, "clear");
    renderAuthGate(queryClient);

    await waitFor(() => expect(authStateChanged).toBeDefined());
    authStateChanged?.({ uid: "first-user" });
    expect(await screen.findByText("Private shopping data")).toBeInTheDocument();

    queryClient.setQueryData(["private-project"], { title: "Private" });
    window.sessionStorage.setItem("private-session", "private");
    authStateChanged?.({ uid: "second-user" });
    expect(clear).toHaveBeenCalledOnce();
    expect(queryClient.getQueryData(["private-project"])).toBeUndefined();
    expect(window.sessionStorage.getItem("private-session")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(mocks.signOut).toHaveBeenCalledOnce();
    authStateChanged?.(null);
    expect(await screen.findByRole("button", { name: "Sign in" })).toBeInTheDocument();
  });

  it("sends Firebase bearer tokens on JSON requests and authenticated streams", async () => {
    mocks.auth.currentUser = { getIdToken: vi.fn().mockResolvedValue("private-token") };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ items: [] }) })
      .mockResolvedValueOnce(
        new Response(new ReadableStream<Uint8Array>({ start: (controller) => controller.close() })),
      );
    vi.stubGlobal("fetch", fetchMock);

    await projectsApi.list();
    const controller = new AbortController();
    await projectsApi.streamMessage("project-id", "message-id", vi.fn(), controller.signal);

    const jsonHeaders = new Headers(fetchMock.mock.calls[0][1]?.headers);
    const streamHeaders = new Headers(fetchMock.mock.calls[1][1]?.headers);
    expect(jsonHeaders.get("Authorization")).toBe("Bearer private-token");
    expect(streamHeaders.get("Authorization")).toBe("Bearer private-token");
    expect(fetchMock.mock.calls[1][0]).not.toContain("private-token");
  });
});
