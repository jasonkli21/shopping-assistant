import { dirname } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { defineConfig } from "playwright/test";

const webRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: { timeout: 15_000 },
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  outputDir: "test-results",
  use: {
    baseURL: "http://127.0.0.1:5173",
    browserName: "chromium",
    viewport: { width: 1280, height: 800 },
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH }
      : undefined,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: "bash e2e/api-server.sh",
      cwd: webRoot,
      url: "http://127.0.0.1:8000/ready",
      timeout: 120_000,
      reuseExistingServer: false,
      env: { ...process.env },
    },
    {
      command: "node node_modules/vite/bin/vite.js --host 127.0.0.1",
      cwd: webRoot,
      url: "http://127.0.0.1:5173",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_BASE_URL: "http://127.0.0.1:8000",
        VITE_FIREBASE_API_KEY: "",
        VITE_FIREBASE_AUTH_DOMAIN: "",
        VITE_FIREBASE_PROJECT_ID: "",
        VITE_FIREBASE_APP_ID: "",
      },
    },
  ],
});
