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
  // json as well as html: the flaky check reads it, and a run where something passed only on
  // the second attempt has to come out red — see scripts/flaky-e2e.py
  reporter: ci
    ? [
        ["list"],
        ["html", { open: "never" }],
        ["json", { outputFile: "playwright-report/results.json" }],
      ]
    : [["list"]],
  use: {
    baseURL,
    // the https stand signs its own certificate on purpose — what it exists to check is the
    // platform's behaviour over https, not who signed it. Plain http runs are unaffected.
    ignoreHTTPSErrors: baseURL.startsWith("https://"),
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
    // in CI the retry is the attempt with evidence worth keeping; locally there is no retry,
    // so the failure itself is
    trace: ci ? "on-first-retry" : "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...(devices["Desktop Chrome"] ?? {}) } }],
});
