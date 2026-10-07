import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getApp: vi.fn(() => ({ name: "existing-app" })),
  getApps: vi.fn(() => []),
  initializeApp: vi.fn(() => ({ name: "new-app" })),
  getAuth: vi.fn(() => ({ currentUser: null })),
}));

vi.mock("firebase/app", () => ({
  getApp: mocks.getApp,
  getApps: mocks.getApps,
  initializeApp: mocks.initializeApp,
}));
vi.mock("firebase/auth", () => ({ getAuth: mocks.getAuth }));

afterEach(() => {
  vi.unstubAllEnvs();
  vi.clearAllMocks();
  vi.resetModules();
});

describe("Firebase setup", () => {
  it("initializes Auth only when all public app settings are present", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "public-api-key");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "shopping.example.test");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "shopping-project");
    vi.stubEnv("VITE_FIREBASE_APP_ID", "web-app-id");
    const initialized = { name: "new-app" };
    mocks.getApps.mockReturnValue([]);
    mocks.initializeApp.mockReturnValue(initialized);

    const configured = await import("../src/auth/firebase");
    expect(configured.firebaseConfigured).toBe(true);
    expect(mocks.initializeApp).toHaveBeenCalledWith({
      apiKey: "public-api-key",
      authDomain: "shopping.example.test",
      projectId: "shopping-project",
      appId: "web-app-id",
    });
    expect(mocks.getAuth).toHaveBeenCalledWith(initialized);
    expect(configured.firebaseAuth).toEqual({ currentUser: null });
  });

  it("leaves auth disabled when any required public setting is missing", async () => {
    vi.stubEnv("VITE_FIREBASE_API_KEY", "public-api-key");
    vi.stubEnv("VITE_FIREBASE_AUTH_DOMAIN", "shopping.example.test");
    vi.stubEnv("VITE_FIREBASE_PROJECT_ID", "shopping-project");
    vi.stubEnv("VITE_FIREBASE_APP_ID", "");

    const unconfigured = await import("../src/auth/firebase");
    expect(unconfigured.firebaseConfigured).toBe(false);
    expect(unconfigured.firebaseAuth).toBeNull();
    expect(mocks.initializeApp).not.toHaveBeenCalled();
    expect(mocks.getAuth).not.toHaveBeenCalled();
  });
});
