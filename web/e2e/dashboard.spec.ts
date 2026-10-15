import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, signIn } from "./helpers";

/**
 * The executive dashboard and search (P14-T07), signed in against the real stack. Needs WS_E2E_AUTH=1.
 * Figures are compared with the API's own responses for the same request (reconciliation).
 */
test.skip(process.env.WS_E2E_AUTH !== "1", "needs the full stack (WS_E2E_AUTH=1)");
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
const money = (amount: string, currency: string) => new Intl.NumberFormat("en", { style: "currency", currency }).format(amount as unknown as number);

let page: Page;

test.beforeAll(async ({ browser }) => {
  page = await (await browser.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  await signIn(page, "alice@example.test");
  const portfolio = await api(page, "portfolios", { method: "POST", body: { name: `Dash ${TAG}`, base_currency: "USD" } });
  expect(portfolio.status, JSON.stringify(portfolio.body)).toBe(201);
  const deposit = await api(page, `portfolios/${portfolio.body.id}/transactions`, {
    method: "POST",
    body: { transaction_type: "DEPOSIT", trade_date: new Date(Date.now() - 3 * 86_400_000).toISOString().slice(0, 10), currency: "USD", gross_amount: { amount: "12345.67", currency: "USD" } },
  });
  expect(deposit.status, JSON.stringify(deposit.body)).toBe(201);
  const goal = await api(page, "goals", {
    method: "POST",
    body: {
      name: `Goal ${TAG}`,
      goal_type: "house_deposit",
      target: { amount: "50000.00", currency: "USD" },
      target_date: `${new Date().getFullYear() + 3}-01-01`,
      assumptions: { contribution: { amount: "500.00", currency: "USD" }, returns: { base: "0" } },
    },
  });
  expect(goal.status, JSON.stringify(goal.body)).toBe(201);
});

test("every headline figure equals the API's response for the same request", async () => {
  await page.goto("/home");
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
  const [dashboard, summary, income, goals] = await Promise.all(
    ["dashboard", "portfolios/consolidated/summary", "income/summary", "goals/summary"].map((p) => api(page, p)),
  );
  const d = dashboard.body;
  // A card's heading may carry an info hint in its name, so match the start of the name.
  const card = (name: string) => page.locator("article", { has: page.getByRole("heading", { name: new RegExp(`^${name}( |$)`) }) });
  await expect(card("Net worth")).toContainText(money(d.net_worth.net_worth.amount, d.currency));
  await expect(card("Assets")).toContainText(money(d.net_worth.assets.amount, d.currency));
  await expect(card("Liabilities")).toContainText(money(d.net_worth.liabilities.amount, d.currency));
  await expect(card("Portfolio value")).toContainText(money(summary.body.total_value.amount, summary.body.currency));
  await expect(card("Income, last 12 months")).toContainText(money(income.body.yearly.amount, income.body.currency));
  await expect(card("Goals")).toContainText(`${goals.body.on_track} of ${goals.body.total} on track`);
});

test("the allocation, the goal and the recent deposit come from the API", async () => {
  await page.goto("/home");
  const net = (await api(page, "net-worth")).body;
  const cls = net.assets_by_class[0];
  await expect(page.getByRole("list", { name: "Assets by class breakdown" })).toContainText(cls.asset_class);
  await expect(page.getByRole("list", { name: "Assets by class breakdown" })).toContainText(money(cls.value.amount, net.currency));
  // The card lists the API's first four goals, so check the first one the API returns.
  const goals = (await api(page, "goals/summary")).body;
  await expect(page.getByRole("progressbar", { name: `${goals.items[0].name} progress` })).toBeVisible();
  const row = page.getByRole("row", { name: new RegExp(`deposit.*Dash ${TAG}`, "i") });
  await expect(row).toContainText("$12,345.67");
});

test("loading, error, stale, empty and offline states", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await context.newPage();
  await signIn(p, "alice@example.test");

  // Error, then retry.
  let fail = true;
  await p.route("**/api/proxy/dashboard", (route) => (fail ? route.fulfill({ status: 500, body: "{}" }) : route.continue()));
  await p.goto("/home");
  await expect(p.getByRole("alert").filter({ hasText: "Wealth summary could not be loaded." })).toBeVisible();
  fail = false;
  await p.getByRole("button", { name: "Try again" }).first().click();
  await expect(p.locator("article").filter({ has: p.getByRole("heading", { name: /^Net worth/ }) })).toBeVisible();

  // Stale: the API says the figures are incomplete.
  await p.route("**/api/proxy/dashboard", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), complete: false } });
  });
  await p.goto("/home");
  await expect(p.getByText("Some figures are incomplete or out of date")).toBeVisible();
  await expect(p.getByText("Stale", { exact: true }).first()).toBeVisible();
  await p.unroute("**/api/proxy/dashboard");

  // Empty: no assets.
  await p.route("**/api/proxy/net-worth", async (route) => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...(await response.json()), assets_by_class: [] } });
  });
  await p.goto("/home");
  await expect(p.getByText("No assets yet")).toBeVisible();

  // Offline.
  await context.setOffline(true);
  await expect(p.getByText("You are offline.")).toBeVisible();
  await context.setOffline(false);
  await expect(p.getByText("You are offline.")).toHaveCount(0);
  await context.close();
});

test("the layout can be reordered and hidden, saved to the account, and restored", async () => {
  await page.goto("/home");
  await page.getByRole("button", { name: "Customise" }).click();
  await page.getByRole("button", { name: "Move Goals up" }).click();
  await page.getByRole("button", { name: "Move Goals up" }).click();
  await page.getByRole("button", { name: "Hide Portfolio Doctor insights" }).click();
  await expect
    .poll(async () => (await api(page, "me")).body.preferences.dashboard_layout)
    .toEqual({ order: ["wealthSummary", "goals", "metrics", "insight"], hidden: ["insight"] });
  await page.getByRole("button", { name: "Done" }).click();
  await expect(page.getByRole("heading", { name: /^Portfolio Doctor/ })).toHaveCount(0);

  // After a reload the saved layout is applied: the Goals section now sits above Recent activity.
  await page.reload();
  const goalsLink = page.getByRole("link", { name: "All goals" });
  const activity = page.getByRole("heading", { name: "Recent activity" });
  await expect(activity).toBeVisible();
  await expect(goalsLink).toBeVisible();
  const [g, a] = await Promise.all([goalsLink.boundingBox(), activity.boundingBox()]);
  expect(g!.y).toBeLessThan(a!.y);
  await expect(page.getByRole("heading", { name: /^Portfolio Doctor/ })).toHaveCount(0);

  await api(page, "me/preferences", { method: "PATCH", body: { dashboard_layout: { order: ["wealthSummary", "metrics", "insight", "goals"], hidden: [] } } });
});

test("search finds your own records, never another user's, and the palette is keyboard-operable", async ({ browser }) => {
  await page.goto("/home");
  await expect(page.getByLabel("Reporting currency")).toHaveValue(/^[A-Z]{3}$/, { timeout: 20_000 }); // the shell has hydrated
  await page.keyboard.press("Control+k");
  const dialog = page.getByRole("dialog", { name: "Search and commands" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("combobox").fill(`Dash ${TAG}`);
  const mine = dialog.getByRole("option", { name: new RegExp(`Dash ${TAG}`) });
  await expect(mine).toBeVisible();
  await expect(mine).toContainText("Portfolio · USD");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/portfolio$/);
  await expect(dialog).toBeHidden();

  // Pages are commands too.
  await page.keyboard.press("Control+k");
  await dialog.getByRole("combobox").fill("goals");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/goals$/);
  await page.keyboard.press("Control+k");
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();

  // Bob never sees Alice's portfolio or goal.
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  const found = await api(bob, `search?q=${encodeURIComponent(TAG)}`);
  expect(found.status).toBe(200);
  expect(found.body.results).toEqual([]);
  await bob.goto("/home");
  await expect(bob.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
  await expect(bob.getByLabel("Reporting currency")).toHaveValue(/^[A-Z]{3}$/, { timeout: 20_000 }); // the shell has hydrated
  await bob.keyboard.press("Control+k");
  const bobDialog = bob.getByRole("dialog", { name: "Search and commands" });
  await bobDialog.getByRole("combobox").fill(TAG);
  await expect(bobDialog.getByRole("option", { name: new RegExp(TAG) })).toHaveCount(0);
});

test("the dashboard passes axe in Light and in Dark", async () => {
  await page.goto("/home");
  await expect(page.getByRole("progressbar").first()).toBeVisible();
  for (const mode of ["light", "dark"] as const) {
    await page.evaluate((m) => document.documentElement.setAttribute("data-theme-pref", m), mode);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${mode}: ${v.id} (${v.nodes.length})`)).toEqual([]);
  }
});
