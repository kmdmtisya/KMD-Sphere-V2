import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * Net worth, liabilities, history and passive income (P14-T11), signed in against the real stack.
 * Needs WS_E2E_AUTH=1. Figures shown are compared with the API's response for the same request
 * (QG-30.1, web side).
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
const LOAN = `Loan ${TAG}`;
const money = (amount: string, currency: string) =>
  new Intl.NumberFormat("en", { style: "currency", currency }).format(
    amount as unknown as number,
  );
const day = (daysAgo: number) =>
  new Date(Date.now() - daysAgo * 86_400_000).toISOString().slice(0, 10);

let page: Page;
let portfolioId = "";

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}
const card = (p: Page, name: string) =>
  p.locator("article", {
    has: p.getByRole("heading", { name: new RegExp(`^${name}( |$)`) }),
  });

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
  const created = await api(page, "portfolios", {
    method: "POST",
    body: { name: `NW ${TAG}`, base_currency: "USD" },
  });
  expect(created.status).toBe(201);
  portfolioId = created.body.id;
  const asset = await api(page, "assets", {
    method: "POST",
    body: { asset_class: "real_estate", name: `Flat ${TAG}`, currency: "USD" },
  });
  expect(asset.status).toBe(201);
  const post = (body: object) =>
    api(page, `portfolios/${portfolioId}/transactions`, {
      method: "POST",
      body: { currency: "USD", ...body },
    });
  expect(
    (
      await post({
        transaction_type: "DEPOSIT",
        trade_date: day(60),
        gross_amount: { amount: "20000.00", currency: "USD" },
      })
    ).status,
  ).toBe(201);
  expect(
    (
      await post({
        transaction_type: "BUY",
        trade_date: day(50),
        asset_id: asset.body.id,
        quantity: "1",
        unit_price: { amount: "12000.00", currency: "USD" },
      })
    ).status,
  ).toBe(201);
  expect(
    (
      await post({
        transaction_type: "RENT",
        trade_date: day(20),
        asset_id: asset.body.id,
        gross_amount: { amount: "300.00", currency: "USD" },
      })
    ).status,
  ).toBe(201);
});

test("net worth figures equal the API's and the history is drawn", async () => {
  await page.goto("/planning/net-worth");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Net worth" }),
  ).toBeVisible();
  const nw = (await api(page, "net-worth")).body;
  await expect(card(page, "Net worth")).toContainText(
    money(nw.net_worth.amount, nw.currency),
  );
  await expect(card(page, "Assets")).toContainText(
    money(nw.assets.amount, nw.currency),
  );
  await expect(card(page, "Liabilities")).toContainText(
    money(nw.liabilities.amount, nw.currency),
  );
  await expect(
    page.getByRole("region", { name: /^Net worth over time/ }),
  ).toBeVisible();
  const history = (await api(page, "net-worth/history?frequency=monthly")).body;
  expect(history.points.length).toBeGreaterThan(1);
  await expect(page.getByText("About this history")).toBeVisible();
});

test("add, edit and delete a liability; the totals follow the API", async () => {
  await page.getByRole("button", { name: "Add a liability" }).click();
  const drawer = page.getByRole("dialog", { name: "Add a liability" });
  await drawer.getByRole("button", { name: "Add the liability" }).click();
  await expect(drawer.getByText("Give the liability a name.")).toBeVisible();
  await drawer.getByLabel("Name").fill(LOAN);
  await drawer.getByLabel("Balance you owe").fill("2500.00");
  await drawer.getByLabel("Currency").selectOption("USD");
  await drawer.getByRole("button", { name: "Add the liability" }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("cell", { name: LOAN, exact: true })).toBeVisible();
  let nw = (await api(page, "net-worth")).body;
  await expect(card(page, "Liabilities")).toContainText(
    money(nw.liabilities.amount, nw.currency),
  );

  await page.getByRole("button", { name: `Edit ${LOAN}` }).click();
  const edit = page.getByRole("dialog", { name: "Edit liability" });
  await edit.getByLabel("Balance you owe").fill("1000.00");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(edit).toBeHidden();
  nw = (await api(page, "net-worth")).body;
  await expect(card(page, "Liabilities")).toContainText(
    money(nw.liabilities.amount, nw.currency),
  );
  await expect(
    page.getByRole("cell", { name: money("1000", "USD"), exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: `Edit ${LOAN}` }).click();
  await page
    .getByRole("dialog", { name: "Edit liability" })
    .getByRole("button", { name: "Delete" })
    .click();
  await page
    .getByRole("button", { name: "Yes, delete this liability" })
    .click();
  await expect(page.getByRole("cell", { name: LOAN, exact: true })).toHaveCount(0);
});

test("income figures equal the API's", async () => {
  await page.goto("/planning/income");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Income" }),
  ).toBeVisible();
  const summary = (await api(page, "income/summary")).body;
  await expect(card(page, "Per year \\(net\\)")).toContainText(
    money(summary.yearly.amount, summary.currency),
  );
  await expect(card(page, "Per month")).toContainText(
    money(summary.monthly.amount, summary.currency),
  );
  await page.getByLabel("Portfolio", { exact: true }).selectOption(portfolioId);
  const income = (await api(page, `portfolios/${portfolioId}/income`)).body;
  const region = page.getByRole("region", { name: /^The last 12 months/ });
  await expect(region).toContainText(
    money(income.trailing_12m.net.amount, income.currency),
  );
  await expect(page.getByRole("cell", { name: "Rent" })).toBeVisible();
});

test("another user cannot read or change this user's liabilities or portfolio income", async ({
  browser,
}) => {
  const mine = await api(page, "liabilities", {
    method: "POST",
    body: {
      name: `Private ${TAG}`,
      liability_type: "other",
      balance: { amount: "10.00", currency: "USD" },
      balance_as_of: day(1),
    },
  });
  expect(mine.status).toBe(201);
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  expect((await api(bob, `liabilities/${mine.body.id}`)).status).toBe(404);
  expect(
    (await api(bob, `liabilities/${mine.body.id}`, { method: "DELETE" }))
      .status,
  ).toBe(404);
  expect((await api(bob, `portfolios/${portfolioId}/income`)).status).toBe(404);
  const theirs = (await api(bob, "liabilities")).body as { id: string }[];
  expect(theirs.some((l) => l.id === mine.body.id)).toBe(false);
  await api(page, `liabilities/${mine.body.id}`, { method: "DELETE" });
});

test("both pages pass axe in Light and Dark", async () => {
  for (const path of ["/planning/net-worth", "/planning/income"]) {
    await page.goto(path);
    await hydrated(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Loading", { exact: false })).toHaveCount(0, {
      timeout: 15_000,
    });
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
        serious.map((x) => `${path} ${mode}: ${x.id} (${x.nodes.length})`),
      ).toEqual([]);
    }
  }
});
