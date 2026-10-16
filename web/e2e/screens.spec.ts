import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";

import { api, signIn } from "./helpers";

/**
 * Screenshots of every key screen at five widths in both themes (P14-T20.6, QG-35.4, QG-36.1,
 * QG-36.2), written to docs/design/screenshots/p14/after/P14-T20/. Review material, not a test of
 * pixels: it asserts only that each screen drew. Runs with WS_E2E_SCREENSHOTS=1 against the stack
 * with the large demo book (see perf.spec.ts), signed in as bob@example.test.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1" || process.env.WS_E2E_SCREENSHOTS !== "1",
  "needs the full stack and WS_E2E_SCREENSHOTS=1",
);
test.describe.configure({ mode: "serial" });
test.setTimeout(900_000);

const OUT = "../docs/design/screenshots/p14/after/P14-T20";
const WIDTHS = [1440, 1280, 1024, 768, 375];
let page: Page;
let portfolioId = "";

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
  await signIn(page, "bob@example.test");
  const portfolios = (await api(page, "portfolios")).body as {
    id: string;
    name: string;
  }[];
  portfolioId = (
    portfolios.find((p) => p.name.startsWith("Large")) ?? portfolios[0]
  ).id;
  const goals = (await api(page, "goals")).body as unknown[];
  if (goals.length === 0) {
    for (const [name, amount, date] of [
      ["Retirement fund", "500000.00", "2046-01-01"],
      ["House deposit", "60000.00", "2029-06-01"],
    ]) {
      await api(page, "goals", {
        method: "POST",
        body: {
          name,
          goal_type: "wealth",
          target: { amount, currency: "USD" },
          target_date: date,
          target_in_todays_money: false,
          assumptions: {
            contribution: { amount: "800.00", currency: "USD" },
            returns: { base: "6" },
          },
        },
      });
    }
    await api(page, "liabilities", {
      method: "POST",
      body: {
        name: "Mortgage",
        liability_type: "mortgage",
        balance: { amount: "180000.00", currency: "USD" },
        balance_as_of: "2026-09-30",
        interest_rate_percent: "4.25",
      },
    });
  }
});

const SCREENS: {
  name: string;
  path: () => string;
  ready: (p: Page) => Promise<void>;
}[] = [
  {
    name: "home",
    path: () => "/home",
    ready: async (p) =>
      void (await expect(
        p.getByRole("heading", { name: /^Net worth/ }).first(),
      ).toBeVisible({ timeout: 30_000 })),
  },
  {
    name: "portfolio",
    path: () => `/portfolio/${portfolioId}`,
    ready: async (p) =>
      void (await expect(p.getByRole("tab", { name: "Holdings" })).toBeVisible({
        timeout: 30_000,
      })),
  },
  {
    name: "analytics",
    path: () => "/portfolio/analytics",
    ready: async (p) =>
      void (await expect(p.getByRole("region", { name: /^Risk/ })).toBeVisible({
        timeout: 30_000,
      })),
  },
  {
    name: "goals",
    path: () => "/goals",
    ready: async (p) =>
      void (await expect(p.getByRole("article").first()).toBeVisible({
        timeout: 30_000,
      })),
  },
  {
    name: "net-worth",
    path: () => "/planning/net-worth",
    ready: async (p) =>
      void (await expect(
        p.getByRole("region", { name: /^Liabilities/ }),
      ).toBeVisible({ timeout: 30_000 })),
  },
  {
    name: "calculator",
    path: () => "/planning/calculator",
    ready: async (p) =>
      void (await expect(
        p.getByRole("button", { name: "Calculate" }),
      ).toBeVisible({ timeout: 30_000 })),
  },
  {
    name: "copilot",
    path: () => "/ai",
    ready: async (p) =>
      void (await expect(p.getByLabel("Ask a question")).toBeVisible({
        timeout: 30_000,
      })),
  },
  {
    name: "settings",
    path: () => "/settings",
    ready: async (p) =>
      void (await expect(
        p.getByRole("region", { name: /^Profile/ }).getByLabel("Display name"),
      ).toBeVisible({ timeout: 30_000 })),
  },
];

for (const width of WIDTHS) {
  test(`screenshots at ${width} px`, async () => {
    mkdirSync(OUT, { recursive: true });
    await page.setViewportSize({ width, height: width >= 1024 ? 900 : 1000 });
    for (const screen of SCREENS) {
      await page.goto(screen.path());
      await hydrated(page);
      await screen.ready(page);
      if (screen.name === "calculator") {
        await page.getByRole("button", { name: "Calculate" }).click();
        await expect(
          page.getByRole("region", { name: "Base scenario" }),
        ).toBeVisible({ timeout: 30_000 });
      }
      for (const theme of ["light", "dark"] as const) {
        await page.evaluate(
          (m) => document.documentElement.setAttribute("data-theme-pref", m),
          theme,
        );
        await page.waitForTimeout(900);
        await page.screenshot({
          path: `${OUT}/${screen.name}-${theme}-${width}.jpg`,
          type: "jpeg",
          quality: 72,
          fullPage: false,
        });
      }
    }
  });
}
