import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { signIn, settled } from "./helpers";

/**
 * The application shell (P14-T06): signed in, against the real stack. Needs WS_E2E_AUTH=1.
 */
test.skip(process.env.WS_E2E_AUTH !== "1", "needs the full stack (WS_E2E_AUTH=1)");

const WIDTHS = [1440, 1280, 1024, 768, 375];

async function signedInPage(browser: import("@playwright/test").Browser, width = 1440): Promise<Page> {
  const context = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await context.newPage();
  await signIn(page, "alice@example.test");
  await page.goto("/home");
  await expect(page.getByRole("heading", { level: 1, name: "Home" })).toBeVisible();
  return page;
}

test("signed out, the portal pages send you back to the landing page", async ({ page }) => {
  await page.goto("/home");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
});

test("the shell has landmarks, grouped navigation with the active page marked, and no forex entry while the module is off", async ({ browser }) => {
  const page = await signedInPage(browser);
  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("button", { name: "Open the menu" })).toHaveCount(0); // only below 1280 px
  const nav = page.getByRole("navigation", { name: "Main" });
  await expect(nav.getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");
  for (const label of ["Portfolios", "Transactions", "Goals", "Copilot", "Doctor", "Alerts", "Reports", "Settings"]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
  // The entry exists only while the forex module is on (WS_E2E_FOREX=1 runs against such an API).
  await expect(nav.getByRole("link", { name: "Live markets" })).toHaveCount(process.env.WS_E2E_FOREX === "1" ? 1 : 0);
  await expect(nav.getByRole("link", { name: "Operator views" })).toHaveCount(0);
  await expect(page.getByRole("main")).toBeVisible();

  await nav.getByRole("link", { name: "Alerts" }).click();
  await expect(page).toHaveURL(/\/alerts/);
  await expect(page.getByRole("heading", { level: 1, name: "Alerts" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Alerts" })).toHaveAttribute("aria-current", "page");
});

test("an unknown portal page is a 404", async ({ browser }) => {
  const page = await signedInPage(browser);
  // The shell streams, so the status line is already sent; Next marks the page noindex and renders its 404.
  await page.goto("/no-such-page");
  await expect(page.getByText("This page could not be found.")).toBeVisible();
  await expect(page.locator('meta[name="robots"]').first()).toHaveAttribute("content", "noindex");
});

test("the skip link is the first tab stop and moves focus to the main content", async ({ browser }) => {
  const page = await signedInPage(browser);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to the main content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page.locator("main#main")).toBeFocused();
});

test("the top bar shows the account's portfolios, reporting currency, data status and notifications", async ({ browser }) => {
  const page = await signedInPage(browser);
  const bar = page.getByRole("banner");
  await expect(bar.getByLabel("Portfolio")).toBeVisible();
  const currency = bar.getByLabel("Reporting currency");
  await expect(currency).toHaveValue(/^[A-Z]{3}$/, { timeout: 20_000 });
  await expect(bar.getByText(/Data: |Stale|Data status unknown/)).toBeVisible();
  await expect(bar.getByRole("link", { name: /^Notifications/ })).toBeVisible();

  // Changing the reporting currency is saved to the account; put it back afterwards.
  const before = await currency.inputValue();
  const other = before === "EUR" ? "USD" : "EUR";
  await currency.selectOption(other);
  await expect
    .poll(() => page.evaluate(async () => (await (await fetch("/api/proxy/me/currency-preferences")).json()).reporting_currency))
    .toBe(other);
  await currency.selectOption(before);
  await expect
    .poll(() => page.evaluate(async () => (await (await fetch("/api/proxy/me/currency-preferences")).json()).reporting_currency))
    .toBe(before);
});

test("the profile menu holds the appearance choice, settings and sign out", async ({ browser }) => {
  const page = await signedInPage(browser);
  await page.getByRole("button", { name: /^Account menu for / }).click();
  const menu = page.getByRole("group", { name: "Profile" });
  await expect(menu.getByText("alice@example.test").first()).toBeVisible();
  await expect(menu.getByRole("radio", { name: "Dark" })).toBeAttached();
  await expect(menu.getByRole("link", { name: "Settings and security" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(menu).toHaveCount(0);
  await page.getByRole("button", { name: /^Account menu for / }).click();
  await menu.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
});

test("the Copilot panel opens with Ctrl+J, resizes with the keyboard, and closes with Escape", async ({ browser }) => {
  const page = await signedInPage(browser);
  const panel = page.getByRole("complementary", { name: "Copilot" });
  await expect(panel).toHaveCount(0);
  await page.keyboard.press("Control+j");
  await expect(panel).toBeVisible();
  const handle = panel.getByRole("separator", { name: "Resize the Copilot panel" });
  const start = Number(await handle.getAttribute("aria-valuenow"));
  await handle.focus();
  await page.keyboard.press("ArrowLeft");
  expect(Number(await handle.getAttribute("aria-valuenow"))).toBe(start + 20);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});

test("the sidebar collapses to icons on wide screens and the choice is remembered", async ({ browser }) => {
  const page = await signedInPage(browser);
  const nav = page.getByRole("navigation", { name: "Main" });
  const width = async () => (await nav.locator("xpath=..").boundingBox())?.width ?? 0;
  expect(await width()).toBeGreaterThan(200);
  await page.getByRole("button", { name: "Collapse the sidebar" }).click();
  await expect.poll(width).toBeLessThan(100);
  await expect(nav.getByRole("link", { name: "Home" })).toBeVisible(); // still reachable, by icon and name
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand the sidebar" })).toBeVisible();
  expect(await width()).toBeLessThan(100);
  await page.getByRole("button", { name: "Expand the sidebar" }).click();
});

test("medium screens show icons and expand the menu as an overlay; narrow screens use a drawer", async ({ browser }) => {
  const medium = await signedInPage(browser, 1024);
  await medium.getByRole("button", { name: "Open the menu" }).click();
  const dialog = medium.getByRole("dialog", { name: "Menu" });
  await expect(dialog.getByRole("link", { name: "Goals" })).toBeVisible();
  await dialog.getByRole("link", { name: "Goals" }).click();
  await expect(medium).toHaveURL(/\/goals$/);
  await expect(dialog).toHaveCount(0); // navigating closes it

  const narrow = await signedInPage(browser, 375);
  await expect(narrow.getByRole("navigation", { name: "Main" })).toHaveCount(0);
  await narrow.getByRole("button", { name: "Open the menu" }).click();
  await expect(narrow.getByRole("dialog", { name: "Menu" }).getByRole("link", { name: "Portfolios" })).toBeVisible();
  await narrow.keyboard.press("Escape");
  await expect(narrow.getByRole("dialog", { name: "Menu" })).toHaveCount(0);
});

for (const width of WIDTHS) {
  test(`no horizontal overflow at ${width}px`, async ({ browser }) => {
    const page = await signedInPage(browser, width);
    await page.keyboard.press("Control+j");
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });
}

test("at 375 px the top bar is two rows and every filter control stays visible", async ({ browser }) => {
  const page = await signedInPage(browser, 375);
  const header = page.getByRole("banner");
  const portfolio = header.getByLabel("Portfolio");
  const currency = header.getByLabel("Reporting currency");
  await expect(portfolio).toBeVisible();
  await expect(currency).toBeVisible();
  const [p, c, menu, bell] = await Promise.all([
    portfolio.boundingBox(),
    currency.boundingBox(),
    header.getByRole("button", { name: "Open the menu" }).boundingBox(),
    header.getByRole("link", { name: /^Notifications/ }).boundingBox(),
  ]);
  // The two selectors share one row, below the row that holds the menu and the actions.
  expect(Math.abs((p?.y ?? 0) - (c?.y ?? 99))).toBeLessThan(4);
  expect(p!.y).toBeGreaterThan(menu!.y + menu!.height - 1);
  // The menu button and the actions share the first row, so the bar is two rows, not three.
  expect(Math.abs(bell!.y - menu!.y)).toBeLessThan(4);
});

test("the shell passes axe in Light and in Dark", async ({ browser }) => {
  const page = await signedInPage(browser);
  for (const mode of ["light", "dark"] as const) {
    await page.evaluate((m) => document.documentElement.setAttribute("data-theme-pref", m), mode);
    await settled(page);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${mode}: ${v.id} (${v.nodes.length})`)).toEqual([]);
  }
});
