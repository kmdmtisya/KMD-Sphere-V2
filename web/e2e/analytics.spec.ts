import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, signIn, settled } from "./helpers";

/**
 * Financial analytics (P14-T09), signed in against the real stack. Needs WS_E2E_AUTH=1. The figures
 * shown are compared with the API's response for the same request (QG-28.4, QG-30.1 web side).
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const NAME = `Analytics ${Date.now().toString(36)}`;
const money = (amount: string, currency = "USD") =>
  new Intl.NumberFormat("en", { style: "currency", currency }).format(
    amount as unknown as number,
  );

let page: Page;
let portfolioId = "";

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
  const created = await api(page, "portfolios", {
    method: "POST",
    body: { name: NAME, base_currency: "USD" },
  });
  expect(created.status).toBe(201);
  portfolioId = created.body.id;
  const deposit = await api(page, `portfolios/${portfolioId}/transactions`, {
    method: "POST",
    body: {
      transaction_type: "DEPOSIT",
      trade_date: "2026-01-05",
      currency: "USD",
      gross_amount: { amount: "1000.00", currency: "USD" },
    },
  });
  expect(deposit.status).toBe(201);
});

test("performance figures are the API's, and the page explains how they are measured", async () => {
  await page.goto("/portfolio/analytics");
  await hydrated(page);
  await page.getByLabel("Portfolio", { exact: true }).selectOption(portfolioId);
  const perf = (await api(page, `portfolios/${portfolioId}/performance`)).body;
  await expect(
    page.getByRole("heading", { level: 1, name: "Analytics" }),
  ).toBeVisible();
  const card = page.getByRole("region", { name: "Performance" });
  await expect(
    card.getByText(money(perf.total_value.amount)).first(),
  ).toBeVisible();
  await expect(
    card.getByText(money(perf.net_invested.amount)).first(),
  ).toBeVisible();
  await expect(page.getByText("About these figures")).toBeVisible();
});

test("changing the period reloads the value series and risk", async () => {
  const seen: string[] = [];
  page.on("request", (r) => {
    if (r.url().includes(`/risk?`)) seen.push(r.url());
  });
  await page
    .getByRole("radio", { name: "1M", exact: true })
    .check({ force: true });
  await expect
    .poll(() => seen.some((u) => u.includes("frequency=daily")))
    .toBe(true);
  await page
    .getByRole("radio", { name: "5Y", exact: true })
    .check({ force: true });
  await expect
    .poll(() => seen.some((u) => u.includes("frequency=monthly")))
    .toBe(true);
  await expect(page.getByRole("heading", { name: "Risk" })).toBeVisible();
});

test("allocation views switch and agree with the API", async () => {
  const alloc = (await api(page, `portfolios/${portfolioId}/allocation`)).body;
  await expect(page.getByRole("heading", { name: "Allocation" })).toBeVisible();
  await page
    .getByRole("radio", { name: "Currency", exact: true })
    .check({ force: true });
  const first = alloc.currency_exposure.slices[0];
  if (first) {
    const slice = page
      .getByRole("group", { name: "Slices" })
      .getByRole("button", { name: first.key ?? "Unclassified" });
    await slice.click();
    await expect(slice).toHaveAttribute("aria-pressed", "true");
  }
  await expect(
    page.getByRole("region", { name: /^Concentration/ }),
  ).toBeVisible();
});

test("another user cannot read this portfolio's analytics", async ({
  browser,
}) => {
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  for (const part of ["performance", "allocation", "risk"]) {
    expect((await api(bob, `portfolios/${portfolioId}/${part}`)).status).toBe(
      404,
    );
  }
});

test("the page passes axe in Light and Dark", async () => {
  await page.goto("/portfolio/analytics");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { name: "Performance" }),
  ).toBeVisible();
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
    expect(serious.map((x) => `${mode}: ${x.id} (${x.nodes.length})`)).toEqual(
      [],
    );
  }
});
