import { existsSync, readFileSync } from "node:fs";

import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against the production build, run as the standalone server the container uses.
 * In CI the backend e2e server (backend/tests/e2e_server.py, seeded throwaway database) runs beside
 * it and `WS_API_BASE_URL` points at it; `WS_E2E_EXPECT_API=1` then requires the web to reach the
 * API.
 */
const PORT = Number(process.env.WS_WEB_PORT ?? 3100);

/**
 * The BFF's settings for the server under test: the environment (CI), else web/.env.local (written
 * by `python scripts/keycloak_dev.py web-client`). The public URL is the test server's own origin,
 * which the development realm registers as a callback.
 */
function serverEnv(): Record<string, string> {
  const env: Record<string, string> = {};
  if (existsSync(".env.local")) {
    for (const line of readFileSync(".env.local", "utf8").split(/\r?\n/)) {
      const match = /^(WS_[A-Z_]+)=(.*)$/.exec(line.trim());
      if (match) env[match[1]] = match[2];
    }
  }
  for (const [k, v] of Object.entries(process.env)) if (k.startsWith("WS_") && v) env[k] = v;
  env.WS_PUBLIC_URL = `http://127.0.0.1:${PORT}`;
  return env;
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  // Sign-in journeys share a few Keycloak accounts, whose brute-force lockout trips when several workers
  // sign in at once, so the full-stack run is serial.
  workers: process.env.CI || process.env.WS_E2E_AUTH ? 1 : undefined,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
    // Colour transitions would otherwise be caught half-way by the contrast checks after a theme switch.
    reducedMotion: "reduce",
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
    env: serverEnv(),
    timeout: 120_000,
  },
});
