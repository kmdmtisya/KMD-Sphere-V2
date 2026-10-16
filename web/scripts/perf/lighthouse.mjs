// Lighthouse over the signed-in pages (P14-T20.1, QG-31.1/31.2). Not a dependency of the project:
//   npm i --no-save lighthouse@12        (or point LIGHTHOUSE_DIR at an install)
//   WS_PERF_BASE=http://127.0.0.1:3100 WS_PERF_USER=alice@example.test WS_PERF_PASSWORD=... \
//     node scripts/perf/lighthouse.mjs [--out docs/web/perf/lighthouse.json]
// It signs in through the real login page with Chrome (or Edge: WS_PERF_BROWSER=msedge), then runs
// Lighthouse (desktop preset, no network throttling beyond its simulated one) on each page and
// prints the scores and the lab metrics. Numbers are lab measurements on one machine: compare them
// with the budgets, never treat them as field data.
import { createRequire } from "node:module";
import { writeFileSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { pathToFileURL } from "node:url";

import { chromium } from "playwright";

const base = process.env.WS_PERF_BASE ?? "http://127.0.0.1:3100";
const user = process.env.WS_PERF_USER ?? "alice@example.test";
const password = process.env.WS_PERF_PASSWORD ?? "";
const channel = process.env.WS_PERF_BROWSER ?? "chrome";
const port = Number(process.env.WS_PERF_PORT ?? 9333);
const lhDir = process.env.LIGHTHOUSE_DIR ?? process.cwd();
const outIndex = process.argv.indexOf("--out");
const out = outIndex > -1 ? process.argv[outIndex + 1] : null;

const PAGES = (process.env.WS_PERF_PAGES ?? "/home,/portfolio,/portfolio/analytics,/goals,/planning/calculator,/ai,/reports,/settings").split(",");

const require = createRequire(join(lhDir, "noop.js"));
const lighthouse = (await import(pathToFileURL(require.resolve("lighthouse")).href)).default;
const desktop = (await import(pathToFileURL(require.resolve("lighthouse/core/config/desktop-config.js")).href)).default;

// A persistent context is the browser's default profile, which is the one Lighthouse attaches to, so
// the signed-in session cookie is shared with it (a plain new context would be a separate profile).
const profile = mkdtempSync(join(tmpdir(), "ws-perf-"));
const context = await chromium.launchPersistentContext(profile, {
  channel,
  headless: true,
  viewport: { width: 1350, height: 940 },
  args: [`--remote-debugging-port=${port}`],
});
const page = context.pages()[0] ?? (await context.newPage());
await page.goto(base);
await page.getByRole("link", { name: "Sign in" }).click();
await page.locator("#username").fill(user);
await page.locator("#password").fill(password);
await page.locator("#kc-login").click();
await page.getByTestId("signed-in-as").waitFor({ timeout: 30000 });

const rows = [];
for (const path of PAGES) {
  // Warm the page once so the server-side caches and the browser's HTTP cache behave as they do for a returning user.
  await page.goto(base + path);
  await page.waitForTimeout(2500);
  // A run that never painted (the first page after a cold start can do that) is repeated, up to twice.
  let lhr;
  for (let attempt = 0; attempt < 3; attempt++) {
    const result = await lighthouse(
      base + path,
      { port, output: "json", logLevel: "error", onlyCategories: ["performance", "accessibility", "best-practices"], disableStorageReset: true },
      desktop,
    );
    lhr = result.lhr;
    if ((lhr.audits["first-contentful-paint"]?.numericValue ?? 0) > 0) break;
  }
  const audit = (id) => lhr.audits[id]?.numericValue ?? null;
  rows.push({
    path,
    performance: Math.round((lhr.categories.performance.score ?? 0) * 100),
    accessibility: Math.round((lhr.categories.accessibility.score ?? 0) * 100),
    bestPractices: Math.round((lhr.categories["best-practices"].score ?? 0) * 100),
    lcpMs: Math.round(audit("largest-contentful-paint")),
    fcpMs: Math.round(audit("first-contentful-paint")),
    cls: Number((audit("cumulative-layout-shift") ?? 0).toFixed(3)),
    tbtMs: Math.round(audit("total-blocking-time")),
    speedIndexMs: Math.round(audit("speed-index")),
    transferKb: Math.round((audit("total-byte-weight") ?? 0) / 1024),
    finalUrl: lhr.finalDisplayedUrl.replace(base, ""),
    // What to look at when a budget is missed: the elements that shifted and the best-practice audits that failed.
    shifts: (lhr.audits["layout-shifts"]?.details?.items ?? []).slice(0, 3).map((i) => `${(i.node?.selector ?? "?").slice(0, 70)} (${Number(i.score ?? 0).toFixed(3)})`),
    bestPracticeFailures: Object.values(lhr.audits)
      .filter((a) => lhr.categories["best-practices"].auditRefs.some((r) => r.id === a.id) && a.score !== null && a.score < 1 && a.scoreDisplayMode !== "informative")
      .map((a) => a.id),
  });
  console.log(JSON.stringify(rows.at(-1)));
}
await context.close();
rmSync(profile, { recursive: true, force: true });
if (out) {
  mkdirSync(dirname(out), { recursive: true });
  writeFileSync(out, JSON.stringify({ measuredAt: new Date().toISOString(), browser: channel, base, pages: rows }, null, 2));
}
