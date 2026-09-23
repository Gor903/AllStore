import { defineConfig, devices } from "@playwright/test";

/**
 * The stack under test is the compose stack, not a server Playwright starts: e2e is here to
 * catch what only shows up when nginx, backend, frontend and Postgres are wired together.
 * See e2e/README.md for how to bring it up.
 *
 * The address is the marketplace host and has to match NEXT_PUBLIC_API_URL of the stack —
 * the browser-side client posts there, and a mismatched host would fail on CORS and on a
 * SameSite cookie rather than on the thing under test. Storefronts are reached by following
 * the links the app itself renders.
 */
const baseURL = process.env["E2E_BASE_URL"] ?? "http://localhost:8080";
const ci = process.env["CI"] !== undefined;

export default defineConfig({
  testDir: "./e2e",
  // one browser against one shared stack: parallel runs would moderate each other's queues
  workers: 1,
  fullyParallel: false,
  forbidOnly: ci,
  retries: ci ? 1 : 0,
  // the stack runs Next.js in dev mode, so a route pays for its first compile
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: ci ? [["list"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL,
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...(devices["Desktop Chrome"] ?? {}) } }],
});
