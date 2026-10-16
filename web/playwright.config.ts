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
  for (const [k, v] of Object.entries(process.env))
    if (k.startsWith("WS_") && v) env[k] = v;
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
  },
  // Chromium runs the whole suite. WS_BROWSERS (comma separated: msedge, firefox, webkit) adds the
  // other supported browsers (P14-T20.4), which run the cross-browser journeys only
  // (e2e/browsers.spec.ts) at five widths in both themes. WS_PLAYWRIGHT_CHANNEL=chrome uses an installed
  // Google Chrome where the bundled browser cannot be downloaded (for example behind TLS
  // interception); CI uses the bundled browsers. WebKit (Safari's engine) works only over HTTPS here,
  // because it will not store the portal's __Host- Secure cookies over plain HTTP; it is not in CI yet.
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        channel: process.env.WS_PLAYWRIGHT_CHANNEL || undefined,
      },
    },
    ...(process.env.WS_BROWSERS ?? "")
      .split(",")
      .map((b) => b.trim())
      .filter(Boolean)
      .map((name) => {
        const device =
          name === "msedge"
            ? devices["Desktop Edge"]
            : name === "firefox"
              ? devices["Desktop Firefox"]
              : devices["Desktop Safari"];
        return {
          name,
          testMatch: /browsers\.spec\.ts/,
          use: {
            ...device,
            ...(name === "msedge" ? { channel: "msedge" } : {}),
          },
        };
      }),
  ],
  webServer: {
    command: `npm run start:standalone -- --port ${PORT} --hostname 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/api/health`,
    reuseExistingServer: !process.env.CI,
    env: serverEnv(),
    timeout: 120_000,
  },
});
