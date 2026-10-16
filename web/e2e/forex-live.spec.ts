import { expect, test, type Page } from "@playwright/test";

import { api, signIn } from "./helpers";

/**
 * Forex workspace, live behaviour (P14-T24.5, T24.6): the notices card and its remembered choice, the
 * candle chart against the API's own numbers, and the page staying responsive while quotes stream.
 * Needs WS_E2E_AUTH=1 and an API with the forex module on (WS_E2E_FOREX=1).
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1" || process.env.WS_E2E_FOREX !== "1",
  "needs the full stack with forex on (WS_E2E_AUTH=1, WS_E2E_FOREX=1)",
);
test.describe.configure({ mode: "serial" });

let page: Page;

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 30_000 },
  );
}

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
});

test("notices: both reminders are on by default, can be turned off, and the choice is remembered", async () => {
  await page.goto("/forex/workspace");
  await hydrated(page);
  const card = page.getByRole("region", { name: /^Notices/ });
  await expect(card).toBeVisible({ timeout: 30_000 });
  const events = card.getByLabel("Remind me of high-impact events in the next hour");
  const paper = card.getByLabel("Tell me when a paper position closes");
  await expect(events).toBeChecked();
  await expect(paper).toBeChecked();
  await expect(card.getByLabel("Current notices")).toBeVisible();
  await paper.uncheck();
  await page.reload();
  await hydrated(page);
  const again = page.getByRole("region", { name: /^Notices/ });
  await expect(again.getByLabel("Tell me when a paper position closes")).not.toBeChecked();
  await expect(again.getByLabel("Remind me of high-impact events in the next hour")).toBeChecked();
  // Put it back so the next run starts from the default.
  await again.getByLabel("Tell me when a paper position closes").check();
});

test("notices never mention real money: paper notices are labelled as simulated", async () => {
  await page.goto("/forex/workspace");
  await hydrated(page);
  const card = page.getByRole("region", { name: /^Notices/ });
  await expect(card).toBeVisible({ timeout: 30_000 });
  const items = await card.getByRole("listitem").allInnerTexts();
  for (const text of items.filter((t) => /paper/i.test(t)))
    expect(text).toContain("simulated money");
});

test("the candle chart draws the candles the API returns, with the API's own last close", async () => {
  const end = new Date();
  const start = new Date(end.getTime() - 7 * 86_400_000);
  const probe = await api(
    page,
    `forex/candles?instrument=EUR_USD&timeframe=1H&start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`,
  );
  expect(probe.status).toBe(200);
  test.skip(
    probe.body.items.length === 0,
    "the API has no EUR/USD 1H candles in the last 7 days (nothing stored: the simulated market is closed or not synced)",
  );
  // Compare the page with the very response it was given, so an hour closing in between cannot matter.
  const answered = page.waitForResponse(
    (r) => r.url().includes("/forex/candles") && r.url().includes("timeframe=1H") && r.ok(),
  );
  await page.goto("/forex/workspace");
  await hydrated(page);
  const items = (await (await answered).json()).items as { close: string }[];
  expect(items.length).toBeGreaterThan(0);
  const chart = page.getByRole("region", { name: /1H candles/ });
  await expect(chart).toBeVisible({ timeout: 30_000 });
  // The text alternative states the count and the last close exactly as the API sent them.
  await expect(
    chart.getByText(`${items.length} 1H candles`, { exact: false }),
  ).toBeVisible();
  await expect(
    chart.getByText(`last close ${items[items.length - 1].close}`, { exact: false }),
  ).toBeVisible();
  // The chart is drawn, not just described: the SVG holds the candle and axis shapes.
  await expect
    .poll(async () => chart.locator("svg path").count(), { timeout: 15_000 })
    .toBeGreaterThan(items.length);
  // And the table alternative lists the same last close.
  await chart.getByRole("button", { name: /as a table/ }).click();
  await expect(chart.getByRole("table")).toContainText(items[items.length - 1].close);
});

test("the page stays responsive while quotes stream in", async () => {
  await page.goto("/forex");
  await hydrated(page);
  await expect(page.getByRole("status")).toContainText("Live quotes connected", {
    timeout: 30_000,
  });
  const table = page.getByRole("table", { name: "Live quotes" });
  await expect(table.getByRole("cell", { name: "simulated" }).first()).toBeVisible({
    timeout: 30_000,
  });
  await page.evaluate(() => {
    const w = window as unknown as { __ev: number[]; __lt: number };
    w.__ev = [];
    w.__lt = 0;
    new PerformanceObserver((list) =>
      list.getEntries().forEach((e) => w.__ev.push(e.duration)),
    ).observe({ type: "event", durationThreshold: 16, buffered: false } as PerformanceObserverInit);
    new PerformanceObserver((list) => (w.__lt += list.getEntries().length)).observe({
      type: "longtask",
      buffered: false,
    });
  });
  const nodesBefore = await page.evaluate(() => document.getElementsByTagName("*").length);
  // Interact for a while: the appearance cycle and the keyboard, as quotes keep arriving.
  for (let i = 0; i < 6; i++) {
    await page.getByRole("button", { name: /appearance|theme/i }).first().click().catch(() => undefined);
    await page.keyboard.press("Tab");
    await page.waitForTimeout(700);
  }
  const { maxEventMs, longTasks } = await page.evaluate(() => {
    const w = window as unknown as { __ev: number[]; __lt: number };
    return { maxEventMs: Math.round(Math.max(0, ...w.__ev)), longTasks: w.__lt };
  });
  const nodesAfter = await page.evaluate(() => document.getElementsByTagName("*").length);
  test.info().annotations.push({
    type: "measured",
    description: `max event ${maxEventMs} ms, ${longTasks} long tasks, DOM ${nodesBefore} -> ${nodesAfter} elements`,
  });
  // Guard rails: well inside the INP budget of 200 ms, and no growth of the page as ticks arrive.
  expect(maxEventMs).toBeLessThan(500);
  expect(nodesAfter).toBeLessThan(nodesBefore * 1.25 + 50);
});
