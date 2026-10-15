import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { settled } from "./helpers";

/**
 * The design-system gallery (P14-T03): accessibility in both themes, behaviour of the interactive
 * components, no horizontal overflow at the five reference widths, and screenshots for review
 * (attached to the report; the before-and-after sets are in docs/design/screenshots/p14).
 * Needs a build made with WS_ENABLE_GALLERY=1.
 */
const WIDTHS = [1440, 1280, 1024, 768, 375];

test.beforeEach(async ({ page }) => {
  const response = await page.goto("/_gallery");
  test.skip(response?.status() === 404, "gallery not included in this build (WS_ENABLE_GALLERY unset)");
});

test("no serious or critical axe violations in the light and dark panels", async ({ page }) => {
  for (const theme of ["light", "dark"]) {
    await settled(page);
    const results = await new AxeBuilder({ page })
      .include(`section[data-theme-pref="${theme}"]`)
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${theme}: ${v.id} (${v.nodes.length})`)).toEqual([]);
  }
});

test("money columns sort exactly and announce the order", async ({ page }) => {
  const panel = page.locator('section[data-theme-pref="light"]');
  const header = panel.getByRole("columnheader", { name: /Market value/ });
  await expect(header).toHaveAttribute("aria-sort", "none");
  await header.getByRole("button").click();
  await expect(header).toHaveAttribute("aria-sort", /ascending|descending/);
  const order = await header.getAttribute("aria-sort");
  const values = await panel.locator("table tbody tr td:nth-child(3)").allInnerTexts();
  const expected = ["$5,039.50", "$12,038.83", "$20,018.05", "$25,142.45", "$29,537.12", "$48,210.40"];
  expect(values).toEqual(order === "ascending" ? expected : [...expected].reverse());
});

test("a chart can be read as a table", async ({ page }) => {
  const panel = page.locator('section[data-theme-pref="dark"]');
  await panel.getByRole("button", { name: "Show Wealth over time as a table" }).click();
  const table = panel.getByRole("table", { name: "Wealth over time" });
  await expect(table).toBeVisible();
  await expect(table.getByRole("row", { name: /Oct 9/ })).toContainText("$139,986.35");
});

test("the period selector is a keyboard-operable radio group", async ({ page }) => {
  const group = page.locator('section[data-theme-pref="light"]').getByRole("group", { name: "Period" });
  await group.getByRole("radio", { name: "1M" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(group.getByRole("radio", { name: "1Y" })).toBeChecked();
});

for (const width of WIDTHS) {
  test(`no horizontal page overflow at ${width}px, light and dark screenshots`, async ({ page }, info) => {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(300);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    for (const theme of ["light", "dark"]) {
      const shot = await page.locator(`section[data-theme-pref="${theme}"]`).screenshot();
      await info.attach(`gallery-${theme}-${width}.png`, { body: shot, contentType: "image/png" });
    }
  });
}
