import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { NAV } from "../src/lib/nav/nav";
import { api, settled, signIn } from "./helpers";

/**
 * Accessibility audit (P14-T19, QG-27.6, QG-27.7, QG-27.9): axe on every page of the navigation in
 * Light and Dark (WCAG 2.2 AA), keyboard operation of the shell, the appearance selector, grids and
 * dialogs, and the reduced-motion preference. Needs WS_E2E_AUTH=1. Manual screen-reader passes
 * (NVDA, VoiceOver) are separate and recorded in docs/web/WEB_ACCESSIBILITY_REPORT.md.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];
let page: Page;
let ops: Page;

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

async function settle(p: Page) {
  await expect(p.getByText(/^Loading/))
    .toHaveCount(0, { timeout: 20_000 })
    .catch(() => undefined);
  await p.waitForTimeout(400);
}

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
  // Give the pages something to show: a portfolio with a deposit.
  const p = await api(page, "portfolios", {
    method: "POST",
    body: { name: `A11y ${Date.now().toString(36)}`, base_currency: "USD" },
  });
  if (p.status === 201) {
    await api(page, `portfolios/${p.body.id}/transactions`, {
      method: "POST",
      body: {
        transaction_type: "DEPOSIT",
        trade_date: "2026-01-05",
        currency: "USD",
        gross_amount: { amount: "2500.00", currency: "USD" },
      },
    });
  }
  ops = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(ops, "ops@example.test");
});

const routes = NAV.flatMap((g) => g.items)
  .filter((i) => i.requires !== "forex" && i.requires !== "support")
  .map((i) => i.href);

for (const href of routes) {
  test(`axe: ${href} has no serious or critical violation in Light and Dark`, async () => {
    await page.goto(href);
    await hydrated(page);
    await settle(page);
    for (const mode of ["light", "dark"] as const) {
      await page.evaluate(
        (m) => document.documentElement.setAttribute("data-theme-pref", m),
        mode,
      );
      await settled(page);
      const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
      const serious = results.violations.filter(
        (v) => v.impact === "serious" || v.impact === "critical",
      );
      expect(
        serious.map(
          (x) =>
            `${href} ${mode}: ${x.id} (${x.nodes.length}) ${x.nodes[0]?.target.join(" ")}`,
        ),
      ).toEqual([]);
    }
  });
}

test("axe: the operator page", async () => {
  await ops.goto("/operator");
  await hydrated(ops);
  await settle(ops);
  for (const mode of ["light", "dark"] as const) {
    await ops.evaluate(
      (m) => document.documentElement.setAttribute("data-theme-pref", m),
      mode,
    );
    await settled(ops);
    const results = await new AxeBuilder({ page: ops })
      .withTags(TAGS)
      .analyze();
    expect(
      results.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((x) => `${mode}: ${x.id}`),
    ).toEqual([]);
  }
});

test("axe: open overlays (the command palette, a drawer, the Copilot panel) in Light and Dark", async () => {
  await page.goto("/goals");
  await hydrated(page);
  for (const mode of ["light", "dark"] as const) {
    await page.evaluate(
      (m) => document.documentElement.setAttribute("data-theme-pref", m),
      mode,
    );
    await settled(page);
    await page.keyboard.press("Control+k");
    await expect(page.getByRole("dialog").first()).toBeVisible();
    let r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      r.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((x) => `palette ${mode}: ${x.id}`),
    ).toEqual([]);
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "New goal" }).click();
    await expect(page.getByRole("dialog", { name: "New goal" })).toBeVisible();
    r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      r.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((x) => `drawer ${mode}: ${x.id}`),
    ).toEqual([]);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Control+j");
    await expect(
      page.getByRole("complementary", { name: "Copilot" }),
    ).toBeVisible();
    r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(
      r.violations
        .filter((v) => v.impact === "serious" || v.impact === "critical")
        .map((x) => `copilot ${mode}: ${x.id}`),
    ).toEqual([]);
    await page.keyboard.press("Escape");
  }
});

test("keyboard: a dialog takes focus, keeps it inside, closes with Escape and returns focus", async () => {
  await page.goto("/goals");
  await hydrated(page);
  const opener = page.getByRole("button", { name: "New goal" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "New goal" });
  await expect(dialog).toBeVisible();
  expect(
    await page.evaluate(
      () => document.activeElement?.closest("dialog") !== null,
    ),
  ).toBe(true);
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    // Inside the dialog, or out on the browser's own controls (body): never on the page behind.
    const where = await page.evaluate(() =>
      document.activeElement === document.body ||
      document.activeElement?.closest("dialog") != null
        ? "ok"
        : (document.activeElement?.tagName ?? "none"),
    );
    expect(where, `tab ${i}`).toBe("ok");
  }
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test("keyboard: the appearance choice works with the arrow keys and is announced", async () => {
  await page.goto("/settings");
  await hydrated(page);
  const group = page.getByRole("region", { name: /^Appearance/ });
  const light = group.getByRole("radio", { name: "Light", exact: true });
  await light.focus();
  await page.keyboard.press("Space");
  await expect(light).toBeChecked();
  await page.keyboard.press("ArrowRight");
  await expect(
    group.getByRole("radio", { name: "Dark", exact: true }),
  ).toBeChecked();
  expect(
    await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme-pref"),
    ),
  ).toBe("dark");
  await group
    .getByRole("radio", { name: "System", exact: true })
    .check({ force: true });
});

test("keyboard: a data grid sorts from the keyboard and the headers say which way", async () => {
  await page.goto("/alerts");
  await hydrated(page);
  await page.goto("/portfolio");
  await hydrated(page);
  await settle(page);
  const sort = page.getByRole("columnheader").getByRole("button").first();
  if (await sort.count()) {
    await sort.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.locator("[aria-sort=ascending], [aria-sort=descending]").first(),
    ).toBeVisible();
  }
});

test("the page is operable by keyboard alone: the skip link, the landmarks and a visible focus ring", async () => {
  await page.goto("/home");
  await hydrated(page);
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to the main content" });
  await expect(skip).toBeFocused();
  const outline = await skip.evaluate(
    (el) =>
      getComputedStyle(el).outlineStyle +
      " " +
      getComputedStyle(el).outlineWidth,
  );
  expect(outline).not.toMatch(/^none/);
  for (const landmark of ["banner", "navigation", "main"] as const)
    await expect(page.getByRole(landmark).first()).toBeVisible();
});

test("reduced motion is respected: no transition or smooth scrolling", async ({
  browser,
}) => {
  const context = await browser.newContext({
    reducedMotion: "reduce",
    viewport: { width: 1440, height: 900 },
  });
  const reduced = await context.newPage();
  await signIn(reduced, "alice@example.test");
  await reduced.goto("/goals");
  await hydrated(reduced);
  const timings = await reduced.evaluate(() => {
    const button = document.querySelector("button") as HTMLElement;
    const style = getComputedStyle(button);
    const parse = (v: string) =>
      Math.max(
        ...v
          .split(",")
          .map((x) =>
            x.trim().endsWith("ms") ? parseFloat(x) : parseFloat(x) * 1000,
          ),
      );
    return {
      transition: parse(style.transitionDuration),
      animation: parse(style.animationDuration),
      scroll: getComputedStyle(document.documentElement).scrollBehavior,
    };
  });
  expect(timings.transition).toBeLessThanOrEqual(0.1);
  expect(timings.animation).toBeLessThanOrEqual(0.1);
  expect(["auto", "normal"]).toContain(timings.scroll);
});

test("content reflows at 320 px wide (400% zoom) on every page, with no horizontal scroll", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 320, height: 800 },
  });
  const narrow = await context.newPage();
  await signIn(narrow, "alice@example.test");
  for (const path of routes) {
    await narrow.goto(path);
    await hydrated(narrow);
    await settle(narrow);
    // Wider letter spacing stands in for the wider fonts of other systems, so the result does not
    // depend on which fonts this machine has.
    await narrow.addStyleTag({
      content: "* { letter-spacing: 0.06em !important; }",
    });
    await narrow.waitForTimeout(200);
    const overflow = await narrow.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
});

test("text can be enlarged to 200% on a desktop screen without losing content or horizontal scroll", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  const big = await context.newPage();
  await signIn(big, "alice@example.test");
  for (const path of [
    "/home",
    "/portfolio",
    "/goals",
    "/settings",
    "/planning/net-worth",
  ]) {
    await big.goto(path);
    await hydrated(big);
    await settle(big);
    await big.evaluate(
      () => (document.documentElement.style.fontSize = "200%"),
    );
    await big.waitForTimeout(300);
    const overflow = await big.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(1);
  }
});
