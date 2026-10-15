import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * Reporting currency, converter and FX status (P14-T14), signed in against the real stack. Needs
 * WS_E2E_AUTH=1. The figures shown are compared with the API's response for the same request
 * (QG-30.2). A fresh test database holds no exchange rates, so the converter is checked both ways:
 * the API's converted amount when a rate exists, and the API's own refusal in words when it does not.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const money = (amount: string, currency: string) =>
  new Intl.NumberFormat("en", { style: "currency", currency }).format(
    amount as unknown as number,
  );

let page: Page;

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

test.beforeAll(async ({ browser }) => {
  page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
});

test("the reporting currency is saved to the account and the page follows it", async () => {
  await page.goto("/planning/currency");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Currency" }),
  ).toBeVisible();
  const before = (await api(page, "me/currency-preferences")).body
    .reporting_currency as string;
  const other = before === "EUR" ? "GBP" : "EUR";
  await page.getByLabel("Show my totals in").selectOption(other);
  await expect
    .poll(
      async () =>
        (await api(page, "me/currency-preferences")).body.reporting_currency,
    )
    .toBe(other);
  await page.getByLabel("Show my totals in").selectOption(before);
  await expect
    .poll(
      async () =>
        (await api(page, "me/currency-preferences")).body.reporting_currency,
    )
    .toBe(before);
});

test("the converter shows the API's amount and rate, or its refusal in words", async () => {
  await page.goto("/planning/currency");
  await hydrated(page);
  const card = page.getByRole("region", { name: /^Converter/ });
  await card.getByLabel("Amount", { exact: true }).fill("100");
  await card.getByLabel("From", { exact: true }).selectOption("USD");
  await card.getByLabel("To", { exact: true }).selectOption("EUR");
  await card.getByRole("button", { name: "Convert" }).click();
  const expected = await api(page, "fx/convert", {
    method: "POST",
    body: { amount: { amount: "100", currency: "USD" }, to: "EUR", on: null },
  });
  if (expected.status === 200) {
    const out = expected.body;
    await expect(card).toContainText(
      money(out.converted.amount, out.converted.currency),
    );
    await expect(card).toContainText(`1 USD = ${out.rate} EUR`);
  } else {
    await expect(card.getByRole("alert")).toBeVisible();
  }
});

test("a malformed amount is explained and nothing is sent", async () => {
  const card = page.getByRole("region", { name: /^Converter/ });
  await card.getByLabel("Amount", { exact: true }).fill("1,000");
  await expect(
    card.getByText("Enter an amount using digits and a decimal point."),
  ).toBeVisible();
  await expect(card.getByRole("button", { name: "Convert" })).toBeDisabled();
  await card.getByLabel("Amount", { exact: true }).fill("100");
});

test("the rate status and history load", async () => {
  await expect(
    page.getByRole("region", { name: /^Exchange-rate status/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: /^Rate history/ }),
  ).toBeVisible();
  const status = (await api(page, "fx/status")).body;
  if (status.rates.length === 0)
    await expect(
      page.getByText("No exchange rates are needed for your accounts yet."),
    ).toBeVisible();
  else
    await expect(
      page.getByRole("table", { name: "Exchange-rate status" }),
    ).toBeVisible();
});

test("the page passes axe in Light and Dark", async () => {
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
    expect(serious.map((x) => `${mode}: ${x.id} (${x.nodes.length})`)).toEqual(
      [],
    );
  }
});
