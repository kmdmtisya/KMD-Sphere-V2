import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the production build, run as the standalone server the container uses.
 * In CI the backend e2e server (backend/tests/e2e_server.py, seeded throwaway database) runs beside
 * it and `WS_API_BASE_URL` points at it; `WS_E2E_EXPECT_API=1` then requires the web to reach the
 * API.
 */
const PORT = Number(process.env.WS_WEB_PORT ?? 3100);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  // Chromium on every run; the full browser matrix (Firefox, WebKit, Edge) arrives with P14-T20.
  // WS_PLAYWRIGHT_CHANNEL=chrome uses an installed Google Chrome where the bundled browser cannot be
  // downloaded (for example behind TLS interception); CI uses the bundled Chromium.
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"], channel: process.env.WS_PLAYWRIGHT_CHANNEL || undefined },
    },
  ],
  webServer: {
    command: `npm run start:standalone -- --port ${PORT} --hostname 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
