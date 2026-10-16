import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

import { api, signIn } from "./helpers";

/**
 * Large-book and responsiveness measurements (P14-T20.2, QG-31.3, QG-31.4), against the real stack.
 * Slow by design (it seeds about 1,500 postings), so it runs only with WS_E2E_PERF=1. It measures
 * on this machine and records the numbers in docs/web/perf/large-book.json; the assertions are
 * generous guard rails (the page must stay usable), not the budgets, which are reported against in
 * docs/web/WEB_PERFORMANCE_REPORT.md.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1" || process.env.WS_E2E_PERF !== "1",
  "needs the full stack and WS_E2E_PERF=1",
);
test.describe.configure({ mode: "serial" });
test.setTimeout(600_000);

const ASSETS = 80;
const POSTINGS = 1500;
let page: Page;
let portfolioId = "";
const results: Record<string, unknown> = {};

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 30_000 },
  );
}

/** Responsiveness: the longest event handling time (an INP-like figure) and long tasks while `act` runs. */
async function interaction(
  p: Page,
  act: () => Promise<void>,
): Promise<{ maxEventMs: number; longTasks: number }> {
  await p.evaluate(() => {
    const w = window as unknown as { __ev: number[]; __lt: number };
    w.__ev = [];
    w.__lt = 0;
    new PerformanceObserver((list) =>
      list.getEntries().forEach((e) => w.__ev.push(e.duration)),
    ).observe({
      type: "event",
      durationThreshold: 16,
      buffered: false,
    } as PerformanceObserverInit);
    new PerformanceObserver(
      (list) => (w.__lt += list.getEntries().length),
    ).observe({ type: "longtask", buffered: false });
  });
  await act();
  await p.waitForTimeout(500);
  return p.evaluate(() => {
    const w = window as unknown as { __ev: number[]; __lt: number };
    return {
      maxEventMs: Math.round(Math.max(0, ...w.__ev)),
      longTasks: w.__lt,
    };
  });
}

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "bob@example.test");
});

test("seed a large book through the API", async () => {
  const tag = Date.now().toString(36);
  const created = await api(page, "portfolios", {
    method: "POST",
    body: { name: `Large ${tag}`, base_currency: "USD" },
  });
  expect(created.status).toBe(201);
  portfolioId = created.body.id;
  const started = Date.now();
  const seeded = await page.evaluate(
    async ({ portfolioId, ASSETS, POSTINGS, tag }) => {
      const csrf = decodeURIComponent(
        /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "",
      );
      const post = async (path: string, body: unknown) => {
        const r = await fetch(`/api/proxy/${path}`, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            "x-csrf-token": csrf,
            "idempotency-key": crypto.randomUUID(),
          },
          body: JSON.stringify(body),
        });
        return { status: r.status, body: await r.json().catch(() => null) };
      };
      const ids: string[] = [];
      for (let i = 0; i < ASSETS; i += 8) {
        const batch = await Promise.all(
          Array.from({ length: Math.min(8, ASSETS - i) }, (_, k) =>
            post("assets", {
              asset_class: "real_estate",
              name: `Perf asset ${tag} ${i + k}`,
              currency: "USD",
            }),
          ),
        );
        for (const b of batch) if (b.status === 201) ids.push(b.body.id);
      }
      const day = (n: number) =>
        new Date(Date.UTC(2024, 0, 1) + n * 86_400_000)
          .toISOString()
          .slice(0, 10);
      await post(`portfolios/${portfolioId}/transactions`, {
        transaction_type: "DEPOSIT",
        trade_date: day(0),
        currency: "USD",
        gross_amount: { amount: "99000000.00", currency: "USD" },
      });
      let ok = 0;
      for (let i = 0; i < POSTINGS; i += 8) {
        const batch = await Promise.all(
          Array.from({ length: Math.min(8, POSTINGS - i) }, (_, k) => {
            const n = i + k;
            const asset = ids[n % ids.length];
            return n < ids.length
              ? post(`portfolios/${portfolioId}/transactions`, {
                  transaction_type: "BUY",
                  trade_date: day(1 + (n % 600)),
                  asset_id: asset,
                  currency: "USD",
                  quantity: "10",
                  unit_price: {
                    amount: `${10 + (n % 90)}.00`,
                    currency: "USD",
                  },
                })
              : post(`portfolios/${portfolioId}/transactions`, {
                  transaction_type: "DIVIDEND",
                  trade_date: day(100 + (n % 500)),
                  asset_id: asset,
                  currency: "USD",
                  gross_amount: {
                    amount: `${1 + (n % 50)}.25`,
                    currency: "USD",
                  },
                });
          }),
        );
        ok += batch.filter((b) => b.status === 201).length;
      }
      return { assets: ids.length, postings: ok };
    },
    { portfolioId, ASSETS, POSTINGS, tag },
  );
  results.seeded = {
    ...seeded,
    seconds: Math.round((Date.now() - started) / 1000),
  };
  expect(seeded.assets).toBe(ASSETS);
  expect(seeded.postings).toBeGreaterThan(POSTINGS * 0.95);
});

test("the holdings table, the ledger and the analytics stay usable on a large book", async () => {
  const timings: Record<string, number> = {};
  const t = async (name: string, path: string, ready: () => Promise<void>) => {
    const start = Date.now();
    await page.goto(path);
    await ready();
    timings[name] = Date.now() - start;
  };
  await t("holdingsPageMs", `/portfolio/${portfolioId}`, async () => {
    await expect(page.getByRole("tab", { name: "Holdings" })).toBeVisible({
      timeout: 60_000,
    });
    await expect(
      page.getByRole("table").first().getByRole("row").nth(5),
    ).toBeVisible({ timeout: 60_000 });
  });
  results.holdingRows = await page
    .getByRole("table")
    .first()
    .getByRole("row")
    .count();
  await t("ledgerPageMs", "/portfolio/transactions", async () => {
    await hydrated(page);
    await expect(
      page.getByRole("table").first().getByRole("row").nth(5),
    ).toBeVisible({ timeout: 60_000 });
  });
  await t("analyticsPageMs", "/portfolio/analytics", async () => {
    await hydrated(page);
    await expect(
      page.getByRole("region", { name: /^Performance/ }),
    ).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("region", { name: /^Risk/ })).toBeVisible({
      timeout: 60_000,
    });
  });
  await t("homePageMs", "/home", async () => {
    await hydrated(page);
    await expect(
      page
        .getByRole("region", { name: /^Key figures|^Portfolio value/ })
        .or(page.locator("article").first()),
    ).toBeVisible({ timeout: 60_000 });
  });
  results.timings = timings;
  for (const [name, ms] of Object.entries(timings))
    expect(ms, name).toBeLessThan(30_000);
});

test("sorting a large grid, changing a chart's period and opening a drawer respond quickly", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await expect(page.getByRole("tab", { name: "Holdings" })).toBeVisible({
    timeout: 60_000,
  });
  const sortHeader = page.getByRole("columnheader").getByRole("button").first();
  const sorting = await interaction(page, async () => {
    await sortHeader.click();
    await sortHeader.click();
  });
  results.sort = sorting;
  const drawer = await interaction(page, async () => {
    await page
      .getByRole("button", { name: "Add a transaction" })
      .first()
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await page.keyboard.press("Escape");
  });
  results.drawer = drawer;
  await page.goto("/portfolio/analytics");
  await hydrated(page);
  await expect(page.getByRole("region", { name: /^Risk/ })).toBeVisible({
    timeout: 60_000,
  });
  const chart = await interaction(page, async () => {
    for (const label of ["1M", "5Y", "All", "1Y"]) {
      await page
        .getByRole("radio", { name: label, exact: true })
        .check({ force: true });
      await page.waitForTimeout(400);
    }
  });
  results.periodChange = chart;
  const heap = await page.evaluate(
    () =>
      (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory
        ?.usedJSHeapSize ?? 0,
  );
  results.jsHeapMb = Math.round(heap / 1_048_576);
  for (const [name, r] of [
    ["sort", sorting],
    ["drawer", drawer],
    ["period", chart],
  ] as const)
    expect(r.maxEventMs, name).toBeLessThan(1000);
});

test("API latency for the dashboard workloads, through the portal", async () => {
  const endpoints = [
    "dashboard",
    "net-worth",
    "portfolios/consolidated/summary",
    "income/summary",
    "goals/summary",
    `portfolios/${portfolioId}/summary`,
    `portfolios/${portfolioId}/holdings`,
    `portfolios/${portfolioId}/performance`,
    `portfolios/${portfolioId}/allocation`,
    `portfolios/${portfolioId}/risk?frequency=monthly`,
    `portfolios/${portfolioId}/transactions?limit=25`,
  ];
  const latency: Record<
    string,
    { coldMs: number; p50Ms: number; p95Ms: number; samples: number }
  > = {};
  for (const path of endpoints) {
    const times = await page.evaluate(async (path) => {
      const out: number[] = [];
      for (let i = 0; i < 30; i++) {
        const t = performance.now();
        const r = await fetch(`/api/proxy/${path}`);
        await r.arrayBuffer();
        if (!r.ok) throw new Error(`${path} answered ${r.status}`);
        out.push(performance.now() - t);
      }
      return out;
    }, path);
    const warm = times.slice(1).sort((a, b) => a - b);
    latency[path.replace(portfolioId, "{id}")] = {
      coldMs: Math.round(times[0]),
      p50Ms: Math.round(warm[Math.floor(warm.length * 0.5)]),
      p95Ms: Math.round(
        warm[Math.min(warm.length - 1, Math.floor(warm.length * 0.95))],
      ),
      samples: warm.length,
    };
  }
  results.apiLatency = latency;
  for (const [path, l] of Object.entries(latency))
    expect(l.p95Ms, path).toBeLessThan(5000);
});

test("record the measurements", async () => {
  mkdirSync("../docs/web/perf", { recursive: true });
  writeFileSync(
    "../docs/web/perf/large-book.json",
    JSON.stringify(
      {
        measuredAt: new Date().toISOString(),
        seededAssets: ASSETS,
        seededPostings: POSTINGS,
        ...results,
      },
      null,
      2,
    ),
  );
});
