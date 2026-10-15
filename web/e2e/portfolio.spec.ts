import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, signIn, settled } from "./helpers";

/**
 * Portfolios, holdings, transactions, valuations and custom assets (P14-T08), signed in against the
 * real stack. Needs WS_E2E_AUTH=1. Totals shown are compared with the API's response for the same
 * request (QG-30.1, web side).
 */
test.skip(process.env.WS_E2E_AUTH !== "1", "needs the full stack (WS_E2E_AUTH=1)");
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
const NAME = `Web ${TAG}`;
const money = (amount: string, currency = "USD") => new Intl.NumberFormat("en", { style: "currency", currency }).format(amount as unknown as number);

let page: Page;
let portfolioId = "";

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(/^[A-Z]{3}$/, { timeout: 20_000 });
}

async function addTransaction(p: Page, type: string, fields: Record<string, string>) {
  await p.getByRole("button", { name: "Add a transaction" }).first().click();
  const drawer = p.getByRole("dialog", { name: /Add a transaction to/ });
  await drawer.getByLabel("Type").selectOption({ label: type });
  for (const [label, value] of Object.entries(fields)) await drawer.getByLabel(label, { exact: true }).fill(value);
  await drawer.getByRole("button", { name: "Add the transaction" }).click();
  await expect(drawer).toBeHidden();
}

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await signIn(page, "alice@example.test");
});

test("create a portfolio from the list, and it opens", async () => {
  await page.goto("/portfolio");
  await hydrated(page);
  await page.getByRole("button", { name: "New portfolio" }).click();
  const drawer = page.getByRole("dialog", { name: "New portfolio" });
  await drawer.getByRole("button", { name: "Create the portfolio" }).click();
  await expect(drawer.getByText("Give the portfolio a name.")).toBeVisible();
  await drawer.getByLabel("Name").fill(NAME);
  await drawer.getByLabel("Currency").selectOption("USD");
  await drawer.getByRole("button", { name: "Create the portfolio" }).click();
  await expect(drawer).toBeHidden();
  await page.getByRole("link", { name: NAME }).click();
  await expect(page.getByRole("heading", { level: 1, name: NAME })).toBeVisible();
  portfolioId = page.url().split("/").pop()!;
  // A second portfolio with the same name is refused with a clear message.
  await page.goto("/portfolio");
  await hydrated(page);
  await page.getByRole("button", { name: "New portfolio" }).click();
  await page.getByRole("dialog", { name: "New portfolio" }).getByLabel("Name").fill(NAME);
  await page.getByRole("dialog", { name: "New portfolio" }).getByRole("button", { name: "Create the portfolio" }).click();
  await expect(page.getByText("You already have a portfolio with this name.")).toBeVisible();
});

test("a deposit appears in the ledger and the totals equal the API's", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await addTransaction(page, "Deposit", { Amount: "10000.00" });
  const summary = (await api(page, `portfolios/${portfolioId}/summary`)).body;
  expect(summary.total_value.amount).toBe("10000.00");
  await expect(page.locator("article", { has: page.getByRole("heading", { name: /^Total value/ }) })).toContainText(money(summary.total_value.amount));
  await expect(page.locator("article", { has: page.getByRole("heading", { name: /^Cash/ }) })).toContainText(money(summary.cash.amount));
  await page.getByRole("tab", { name: "Transactions" }).click();
  await expect(page.getByRole("row", { name: /Deposit/ })).toContainText("$10,000.00");
});

test("form validation, and the server's own refusal, are shown", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await page.getByRole("button", { name: "Add a transaction" }).first().click();
  const drawer = page.getByRole("dialog", { name: /Add a transaction to/ });
  await drawer.getByRole("button", { name: "Add the transaction" }).click(); // a Buy with nothing filled in
  await expect(drawer.getByText("Choose the asset.")).toBeVisible();
  await expect(drawer.getByText("Enter a quantity above zero.")).toBeVisible();
  await drawer.getByLabel("Type").selectOption({ label: "Deposit" });
  await drawer.getByLabel("Amount").fill("10.123");
  await drawer.getByRole("button", { name: "Add the transaction" }).click();
  await expect(drawer.getByRole("alert")).toBeVisible(); // three decimals in dollars: the API refuses, the form shows why
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("a custom asset is created from the picker, bought, valued and shown in the holdings", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  const classes = (await api(page, "asset-classes")).body as { code: string; name: string; valuation_mode: string }[];
  const manual = classes.find((c) => c.valuation_mode === "manual")!;
  await page.getByRole("button", { name: "Add a transaction" }).first().click();
  const drawer = page.getByRole("dialog", { name: /Add a transaction to/ });
  await drawer.getByRole("button", { name: "Create a custom asset" }).click();
  await drawer.getByLabel("Asset class").selectOption(manual.code);
  await drawer.getByLabel("Name", { exact: true }).fill(`Flat ${TAG}`);
  await drawer.getByRole("button", { name: "Create the asset" }).click();
  await expect(drawer.getByText(`Selected: Flat ${TAG}`)).toBeVisible();
  await drawer.getByLabel("Quantity").fill("1");
  await drawer.getByLabel("Price per unit").fill("5000.00");
  await drawer.getByRole("button", { name: "Add the transaction" }).click();
  await expect(drawer).toBeHidden();

  await page.getByRole("tab", { name: "Valuations" }).click();
  await page.getByRole("button", { name: "Add a valuation" }).click();
  const v = page.getByRole("dialog", { name: "Add a valuation" });
  await v.getByLabel("Asset", { exact: true }).fill(`Flat ${TAG}`);
  await v.getByRole("button", { name: new RegExp(`Flat ${TAG}`) }).click();
  await v.getByLabel("Value").fill("6000.00");
  await v.getByRole("button", { name: "Add the valuation" }).click();
  await expect(v).toBeHidden();
  await expect(page.getByRole("row", { name: new RegExp(`Flat ${TAG}`) })).toContainText("$6,000.00");

  await page.getByRole("tab", { name: "Holdings" }).click();
  const holdings = (await api(page, `portfolios/${portfolioId}/holdings`)).body as { asset: { name: string }; value: { amount: string } | null }[];
  const flat = holdings.find((h) => h.asset.name === `Flat ${TAG}`)!;
  await expect(page.getByRole("row", { name: new RegExp(`Flat ${TAG}`) })).toContainText(money(flat.value!.amount));
});

test("a transaction is reversed, not deleted: both stay visible and the totals follow the API", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await page.getByRole("tab", { name: "Transactions" }).click();
  await page.getByRole("row", { name: /Deposit/ }).getByRole("button", { name: /Reverse/ }).click();
  const drawer = page.getByRole("dialog", { name: "Reverse a transaction" });
  await drawer.getByRole("button", { name: "Reverse the transaction" }).click();
  await expect(drawer).toBeHidden();
  await expect(page.getByRole("row", { name: /Deposit.*Reversed/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Deposit.*Reversal/ }).first()).toBeVisible();
  const summary = (await api(page, `portfolios/${portfolioId}/summary`)).body;
  await expect(page.locator("article", { has: page.getByRole("heading", { name: /^Cash/ }) })).toContainText(money(summary.cash.amount));
});

test("the ledger page filters by type, and a column choice is a saved view", async () => {
  await page.goto("/portfolio/transactions");
  await hydrated(page);
  await page.getByLabel("Portfolio", { exact: true }).selectOption({ label: NAME });
  await page.getByLabel("Show").selectOption({ label: "Buy" });
  await expect(page.getByRole("row", { name: /Buy/ })).toBeVisible();
  await expect(page.getByRole("row", { name: /Deposit/ })).toHaveCount(0);

  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await page.getByLabel("Income", { exact: true }).uncheck();
  await expect(page.getByRole("columnheader", { name: /Income/ })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("columnheader", { name: /Realised/ })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: /Income/ })).toHaveCount(0);
  await page.getByLabel("Income", { exact: true }).check();
});

test("another user cannot open the portfolio", async ({ browser }) => {
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  await bob.goto(`/portfolio/${portfolioId}`);
  await expect(bob.getByText("Portfolio not found")).toBeVisible();
  expect((await api(bob, `portfolios/${portfolioId}/transactions`)).status).toBe(404);
});

test("pages pass axe in Light and Dark; an archived portfolio is read-only", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await expect(page.getByRole("tab", { name: "Holdings" })).toBeVisible();
  for (const mode of ["light", "dark"] as const) {
    await page.evaluate((m) => document.documentElement.setAttribute("data-theme-pref", m), mode);
    await settled(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((x) => `${mode}: ${x.id} (${x.nodes.length})`)).toEqual([]);
  }
  await page.getByRole("button", { name: "Archive" }).click();
  await expect(page.getByText("This portfolio is archived: it is read-only.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Add a transaction" }).first()).toBeDisabled();
});
