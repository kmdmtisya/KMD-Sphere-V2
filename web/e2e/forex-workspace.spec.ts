import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * The advanced forex workspace (P14-T24), signed in against the real stack. Needs WS_E2E_AUTH=1.
 * With the forex module off the page is absent; with it on (WS_E2E_FOREX=1 and an API started with
 * FOREX_ENABLED=true FOREX_FEED_ENABLED=true) the panels load, labels are always shown, the paper
 * journey works, there is no real-money order affordance, and paper results never reach wealth figures.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const FOREX_ON = process.env.WS_E2E_FOREX === "1";
let page: Page;

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 30_000 },
  );
}
const tab = (p: Page, name: string) =>
  p.getByRole("radio", { name, exact: true }).check({ force: true });

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
});

test("with the module off the workspace is absent", async () => {
  test.skip(FOREX_ON, "forex is on in this stack");
  await page.goto("/forex/workspace");
  await expect(page).toHaveURL(/\/home$/);
  expect((await api(page, "forex/paper/accounts")).status).toBe(404);
});

test("the workspace says plainly that it places no real trades and shows the feed status", async () => {
  test.skip(!FOREX_ON, "needs an API with forex on (WS_E2E_FOREX=1)");
  await page.goto("/forex/workspace");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Forex workspace" }),
  ).toBeVisible();
  await expect(page.getByRole("status").first()).toContainText(
    "places no real trades",
  );
  await expect(page.getByRole("status").first()).toContainText(
    /Feed (connected|degraded|disconnected)/,
    { timeout: 30_000 },
  );
});

test("analysis shows candles or says there are none, and a labelled forecast", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  const forecast = page.getByRole("region", { name: /^Forecast/ });
  await expect(forecast).toBeVisible({ timeout: 30_000 });
  await expect(
    forecast
      .getByText(/No forecast is available|Requires calibration|Calibrated/)
      .first(),
  ).toBeVisible({ timeout: 30_000 });
  await expect(
    page.getByText(/No candles|candles from|candles of/).first(),
  ).toBeVisible({ timeout: 30_000 });
});

test("opportunities, calendar and backtests load with their notices", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  await tab(page, "Opportunities");
  await expect(
    page.getByText(/not an order and not advice|No setups right now/).first(),
  ).toBeVisible({ timeout: 30_000 });
  await tab(page, "Calendar");
  await expect(
    page.getByText(/About the calendar|No events/).first(),
  ).toBeVisible({ timeout: 30_000 });
  await tab(page, "Backtests");
  await expect(
    page.getByText(/About backtests|No backtests/).first(),
  ).toBeVisible({ timeout: 30_000 });
});

test("the risk calculator shows the position size the backend works out", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  await tab(page, "Risk calculator");
  const card = page.getByRole("region", { name: /^Position risk/ });
  await card.getByLabel("Entry price").fill("1.0850");
  await card.getByLabel("Stop price").fill("1.0800");
  await card.getByRole("button", { name: "Calculate" }).click();
  const reporting = (await api(page, "me/currency-preferences")).body
    .reporting_currency as string;
  const expected = await api(page, "forex/risk/calculate", {
    method: "POST",
    body: {
      instrument: "EUR_USD",
      direction: "long",
      entry: "1.0850",
      stop: "1.0800",
      target: null,
      balance: "10000",
      account_currency: reporting,
      risk_percent: "1",
    },
  });
  if (expected.status === 200)
    await expect(
      page.getByText(`${expected.body.size.lots} lots`).first(),
    ).toBeVisible({ timeout: 30_000 });
  else await expect(page.getByRole("alert").first()).toBeVisible();
  // A wrong-side stop is explained before anything is sent.
  await card.getByLabel("Stop price").fill("1.0900");
  await card.getByRole("button", { name: "Calculate" }).click();
  await expect(card.getByText(/stop is below the entry/)).toBeVisible();
});

test("paper trading: open an account, place a labelled paper order, and it never touches wealth figures", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  const before = (await api(page, "portfolios/consolidated/summary")).body
    .total_value.amount;
  await tab(page, "Paper trading");
  await expect(
    page.getByText("Paper trading · simulated money").first(),
  ).toBeVisible({ timeout: 30_000 });
  const open = page.getByRole("button", { name: "Open a paper account" });
  if (await open.count()) await open.click();
  await expect(
    page.getByRole("region", { name: /^Place a paper order/ }),
  ).toBeVisible({ timeout: 30_000 });
  // Every card in the panel carries the label.
  for (const name of [
    /^Place a paper order/,
    /^Paper positions/,
    /^Paper orders/,
    /^Trading journal/,
  ]) {
    await expect(
      page
        .getByRole("region", { name })
        .getByText("Paper trading · simulated money")
        .first(),
    ).toBeVisible();
  }
  const form = page.getByRole("region", { name: /^Place a paper order/ });
  await form.getByLabel("Stop price").fill("1.0000");
  await form.getByRole("button", { name: "Place paper order" }).click();
  await expect(
    form.getByRole("status").or(form.getByRole("alert")).first(),
  ).toBeVisible({ timeout: 30_000 });
  // The journey continues with a journal note.
  const journal = page.getByRole("region", { name: /^Trading journal/ });
  await journal
    .getByLabel("Note", { exact: true })
    .fill("Practice idea from the e2e run");
  await journal.getByRole("button", { name: "Add the note" }).click();
  await expect(
    journal.getByText("Practice idea from the e2e run").first(),
  ).toBeVisible({ timeout: 30_000 });
  const after = (await api(page, "portfolios/consolidated/summary")).body
    .total_value.amount;
  expect(after).toBe(before);
});

test("there is no way to place a real-money order from the workspace", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  for (const name of [
    "Analysis",
    "Opportunities",
    "Risk calculator",
    "Calendar",
    "Paper trading",
    "Backtests",
  ]) {
    await tab(page, name);
    await page.waitForTimeout(400);
    const buttons = await page.getByRole("button").allInnerTexts();
    const offending = buttons.filter(
      (t) =>
        /\b(buy|sell|trade|invest|deposit|fund)\b/i.test(t) &&
        !/paper/i.test(t),
    );
    expect(offending, name).toEqual([]);
  }
});

test("the workspace passes axe in Light and Dark on its main panels", async () => {
  test.skip(!FOREX_ON, "needs forex on");
  for (const name of ["Analysis", "Paper trading", "Risk calculator"]) {
    await tab(page, name);
    await page.waitForTimeout(1200);
    for (const mode of ["light", "dark"] as const) {
      await page.evaluate(
        (m) => document.documentElement.setAttribute("data-theme-pref", m),
        mode,
      );
      await settled(page);
      const results = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
        .analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(
        serious.map(
          (x) =>
            `${name} ${mode}: ${x.id} (${x.nodes.length}) ${x.nodes[0]?.target.join(" ")}`,
        ),
      ).toEqual([]);
    }
  }
});
