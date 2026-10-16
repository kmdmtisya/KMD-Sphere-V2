import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

/**
 * The cross-browser journeys (P14-T20.4, QG-32): the same checks in every supported browser (the
 * `chromium` project runs them too; Edge, Firefox and WebKit are added with WS_BROWSERS). At five
 * widths and in both themes, the key pages show their content with no unintended horizontal overflow
 * (QG-27.8, QG-32.5); and the main interactions work. Needs WS_E2E_AUTH=1.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const WIDTHS = [1440, 1280, 1024, 768, 375];
const PAGES: { path: string; heading: string }[] = [
  { path: "/home", heading: "Home" },
  { path: "/portfolio", heading: "Portfolios" },
  { path: "/goals", heading: "Goals" },
  { path: "/planning/calculator", heading: "Calculator" },
  { path: "/ai", heading: "Copilot" },
  { path: "/settings", heading: "Settings" },
];

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

for (const width of WIDTHS) {
  for (const theme of ["light", "dark"] as const) {
    test(`pages fit and show their content at ${width} px in ${theme} mode`, async () => {
      await page.setViewportSize({ width, height: 900 });
      for (const { path, heading } of PAGES) {
        await page.goto(path);
        await expect(
          page.getByRole("heading", { level: 1, name: heading }),
        ).toBeVisible({ timeout: 30_000 });
        await page.evaluate(
          (m) => document.documentElement.setAttribute("data-theme-pref", m),
          theme,
        );
        await page.waitForTimeout(250);
        const overflow = await page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        );
        expect(overflow, `${path} at ${width}px`).toBeLessThanOrEqual(1);
        const background = await page.evaluate(
          () => getComputedStyle(document.body).backgroundColor,
        );
        expect(background, `${path} ${theme}`).toBe(
          theme === "dark" ? "rgb(11, 27, 43)" : "rgb(245, 247, 250)",
        );
      }
    });
  }
}

test("the calculator calculates, a drawer opens and closes with Escape, and the palette opens from the keyboard", async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/planning/calculator");
  await hydrated(page);
  await page.getByRole("button", { name: "Calculate" }).click();
  await expect(page.getByRole("region", { name: "Base scenario" })).toBeVisible(
    { timeout: 30_000 },
  );
  await page.goto("/goals");
  await hydrated(page);
  await page.getByRole("button", { name: "New goal" }).click();
  await expect(page.getByRole("dialog", { name: "New goal" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "New goal" })).toBeHidden();
  await page.keyboard.press("Control+k");
  await expect(page.getByRole("dialog").first()).toBeVisible();
  await page.keyboard.press("Escape");
});

test("the appearance choice is applied at once, kept in the cookie and survives a reload", async () => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/settings");
  await hydrated(page);
  const group = page.getByRole("region", { name: /^Appearance/ });
  await group
    .locator("label", {
      has: page.getByRole("radio", { name: "Dark", exact: true }),
    })
    .click();
  expect(
    await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme-pref"),
    ),
  ).toBe("dark");
  await page.reload();
  expect(
    await page.evaluate(() =>
      document.documentElement.getAttribute("data-theme-pref"),
    ),
  ).toBe("dark");
  await hydrated(page);
  await group
    .locator("label", {
      has: page.getByRole("radio", { name: "System", exact: true }),
    })
    .click();
});

test("charts draw and show their table alternative", async () => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/planning/calculator");
  await hydrated(page);
  await page.getByRole("button", { name: "Calculate" }).click();
  await expect(page.locator("canvas, svg").first()).toBeVisible({
    timeout: 30_000,
  });
  await page
    .getByRole("button", { name: /Show Growth by year as a table/ })
    .click();
  await expect(page.getByRole("table").first()).toBeVisible();
});
