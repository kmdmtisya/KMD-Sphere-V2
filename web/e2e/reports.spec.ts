import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

import { api, settled, signIn } from "./helpers";

/**
 * Reports and exports (P14-T15), signed in against the real stack. Needs WS_E2E_AUTH=1. A file's
 * figures are compared with the API's response for the same request (QG-30.1, web side).
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const NAME = `Rep ${Date.now().toString(36)}`;
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
    await browser.newContext({
      viewport: { width: 1440, height: 900 },
      acceptDownloads: true,
    })
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
      gross_amount: { amount: "4200.00", currency: "USD" },
    },
  });
  expect(deposit.status).toBe(201);
});

test("the catalogue lists every report with its formats", async () => {
  await page.goto("/reports");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Reports" }),
  ).toBeVisible();
  for (const title of [
    "Portfolio statement",
    "Performance and allocation",
    "Net worth",
    "Passive income",
    "Goals",
  ]) {
    await expect(
      page.getByRole("article", { name: new RegExp(`^${title}`) }),
    ).toBeVisible();
  }
  await expect(page.getByText("About reports")).toBeVisible();
});

test("a CSV statement downloads and its total equals the API's", async () => {
  await page.goto("/reports");
  await hydrated(page);
  const card = page.getByRole("article", { name: /^Portfolio statement/ });
  await card.getByLabel("Portfolio", { exact: true }).selectOption(portfolioId);
  await card.getByLabel("Format").selectOption("csv");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    card.getByRole("button", { name: /^Download/ }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(
    /^wealthsphere-portfolio-\d{4}-\d{2}-\d{2}\.csv$/,
  );
  const text = readFileSync(await download.path(), "utf8");
  const summary = (await api(page, `portfolios/${portfolioId}/summary`)).body;
  expect(text).toContain(`Total value,${summary.total_value.amount}`);
  expect(text).toContain("not investment, tax or legal advice");
  await expect(card.getByRole("status")).toContainText(
    "Downloaded wealthsphere-portfolio-",
  );
});

test("a PDF and an Excel file download", async () => {
  const card = page.getByRole("article", { name: /^Net worth/ });
  for (const [format, ext, magic] of [
    ["pdf", "pdf", "%PDF"],
    ["xlsx", "xlsx", "PK"],
  ] as const) {
    await card.getByLabel("Format").selectOption(format);
    const [download] = await Promise.all([
      page.waitForEvent("download"),
      card.getByRole("button", { name: /^Download/ }).click(),
    ]);
    expect(download.suggestedFilename()).toMatch(new RegExp(`\\.${ext}$`));
    expect(
      readFileSync(await download.path())
        .subarray(0, magic.length)
        .toString("latin1"),
    ).toBe(magic);
  }
});

test("another user cannot make a report of this portfolio", async ({
  browser,
}) => {
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  for (const kind of ["portfolio", "performance", "income"]) {
    const r = await bob.evaluate(
      async ({ kind, id }) =>
        (
          await fetch(
            `/api/proxy/reports/${kind}?format=csv&portfolio_id=${id}`,
          )
        ).status,
      { kind, id: portfolioId },
    );
    expect(r).toBe(404);
  }
});

test("the page passes axe in Light and Dark", async () => {
  await page.goto("/reports");
  await hydrated(page);
  await expect(page.getByRole("article", { name: /^Goals/ })).toBeVisible({
    timeout: 20_000,
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
    expect(serious.map((x) => `${mode}: ${x.id} (${x.nodes.length})`)).toEqual(
      [],
    );
  }
});
