import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

/**
 * Appearance: Light, Dark and System (P14-T25, QG-36). The scaffold colours are the generated
 * tokens: light `#F5F7FA`, dark `#0B1B2B`.
 */
const LIGHT_BG = "rgb(245, 247, 250)";
const DARK_BG = "rgb(11, 27, 43)";

const background = (page: Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
const preference = (page: Page) => page.evaluate(() => document.documentElement.getAttribute("data-theme-pref"));
const themeCookie = async (page: Page) =>
  (await page.context().cookies(page.url())).find((c) => c.name === "__Host-ws_theme")?.value;

/** Chooses an appearance the way a person does: by clicking its label. */
async function choose(page: Page, name: "Light" | "Dark" | "System"): Promise<void> {
  await page.locator("label", { has: page.getByRole("radio", { name, exact: true }) }).first().click();
}

test("choosing Dark applies at once, is kept in the cookie and survives a reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  expect(await background(page)).toBe(LIGHT_BG);
  await choose(page, "Dark");
  expect(await preference(page)).toBe("dark");
  expect(await background(page)).toBe(DARK_BG);
  expect(await themeCookie(page)).toBe("dark");
  await page.reload();
  expect(await preference(page)).toBe("dark");
  expect(await background(page)).toBe(DARK_BG);
  await expect(page.getByRole("radio", { name: "Dark" })).toBeChecked();
});

test("the first painted frame already shows the saved appearance (no flash)", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await page.evaluate(() => {
    document.cookie = "__Host-ws_theme=dark; Path=/; Max-Age=600; SameSite=Lax; Secure";
  });
  // Records the theme at the very first animation frame of the next load, before React hydrates.
  await page.addInitScript(() => {
    requestAnimationFrame(() => {
      const w = window as unknown as { firstFrame: { pref: string | null; bg: string } };
      w.firstFrame = {
        pref: document.documentElement.getAttribute("data-theme-pref"),
        bg: document.body ? getComputedStyle(document.body).backgroundColor : "",
      };
    });
  });
  await page.reload();
  await page.waitForFunction(() => "firstFrame" in window);
  const first = await page.evaluate(() => (window as unknown as { firstFrame: { pref: string; bg: string } }).firstFrame);
  expect(first.pref).toBe("dark");
  expect(first.bg).toBe(DARK_BG);
});

test("System follows the device while the page is open, and the saved choice stays System", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  await choose(page, "Dark");
  await choose(page, "System");
  expect(await background(page)).toBe(LIGHT_BG);
  await expect(page.getByText("System follows your device (currently Light).")).toBeVisible();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => background(page)).toBe(DARK_BG);
  await expect(page.getByText("System follows your device (currently Dark).")).toBeVisible();
  expect(await preference(page)).toBe("system");
  expect(await themeCookie(page)).toBe("system");
});

test("without JavaScript the page follows the device", async ({ browser, baseURL }) => {
  for (const scheme of ["dark", "light"] as const) {
    const context = await browser.newContext({ javaScriptEnabled: false, colorScheme: scheme });
    const page = await context.newPage();
    await page.goto(`${baseURL}/`);
    expect(await background(page)).toBe(scheme === "dark" ? DARK_BG : LIGHT_BG);
    await context.close();
  }
});

test("another open tab follows the change at once", async ({ context }) => {
  const first = await context.newPage();
  const second = await context.newPage();
  await first.goto("/");
  await second.goto("/");
  await choose(first, "Light");
  await expect.poll(() => preference(second)).toBe("light");
  await choose(first, "Dark");
  await expect.poll(() => preference(second)).toBe("dark");
  await expect.poll(() => background(second)).toBe(DARK_BG);
});

test("charts, tables and dialogs follow the appearance", async ({ page }) => {
  const response = await page.goto("/_gallery");
  test.skip(response?.status() === 404, "gallery not included in this build (WS_ENABLE_GALLERY unset)");
  const panel = page.getByTestId("following-panel");
  const line = panel.locator("svg path[stroke]").first();
  const dialog = panel.getByRole("dialog", { name: "Example dialog" });
  const stroke = () => line.getAttribute("stroke");
  const dialogBg = () => dialog.evaluate((el) => getComputedStyle(el).backgroundColor);

  await choose(page, "Light");
  await expect.poll(stroke).not.toBeNull();
  const lightStroke = await stroke();
  const lightDialog = await dialogBg();
  await choose(page, "Dark");
  await expect.poll(stroke).not.toBe(lightStroke);
  expect(await dialogBg()).not.toBe(lightDialog);
});

test("the selector works with the keyboard and the cycle button says what it does", async ({ page }) => {
  await page.goto("/");
  await choose(page, "Light");
  await page.getByRole("radio", { name: "Light", exact: true }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "Dark" })).toBeChecked();
  expect(await preference(page)).toBe("dark");
  const cycle = page.getByRole("button", { name: /^Appearance: Dark\. Switch to System$/ });
  await cycle.click();
  expect(await preference(page)).toBe("system");
  await expect(page.getByRole("button", { name: /^Appearance: System \((Light|Dark)\)\. Switch to Light$/ })).toBeVisible();
});

test("the appearance controls pass axe in Light and in Dark", async ({ page }) => {
  await page.goto("/");
  for (const mode of ["Light", "Dark"] as const) {
    await choose(page, mode);
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${mode}: ${v.id}`)).toEqual([]);
  }
});

// ---------------------------------------------------------------- with an account (full stack)

const AUTH = process.env.WS_E2E_AUTH === "1";

test("signed in, the choice is saved to the account and another device starts with it", async ({ browser }) => {
  test.skip(!AUTH, "needs the full stack (WS_E2E_AUTH=1)");
  const desk = await (await browser.newContext({ colorScheme: "light" })).newPage();
  await signIn(desk, "bob@example.test");
  await choose(desk, "Dark");
  await expect
    .poll(async () => desk.evaluate(async () => (await (await fetch("/api/proxy/me")).json()).preferences?.theme_mode))
    .toBe("dark");

  // A new browser with no cookie: after sign-in, the account's choice is applied.
  const laptop = await (await browser.newContext({ colorScheme: "light" })).newPage();
  await signIn(laptop, "bob@example.test");
  expect(await preference(laptop)).toBe("dark");
  expect(await background(laptop)).toBe(DARK_BG);

  // Leave the account as System for other runs.
  await choose(laptop, "System");
  await expect
    .poll(async () => laptop.evaluate(async () => (await (await fetch("/api/proxy/me")).json()).preferences?.theme_mode))
    .toBe("system");
});
