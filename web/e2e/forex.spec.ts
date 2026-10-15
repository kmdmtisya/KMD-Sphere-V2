import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * The live-markets entry (P14-T13). Needs WS_E2E_AUTH=1. With the forex module off (the CI stack)
 * the entry, the page and the ticket route are absent. With it on (WS_E2E_FOREX=1 and an API started
 * with FOREX_ENABLED=true FOREX_FEED_ENABLED=true) the page connects with a single-use ticket and
 * shows quotes.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const FOREX_ON = process.env.WS_E2E_FOREX === "1";
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

test("the stream address is given to a signed-in browser only, and carries no secret", async ({
  browser,
}) => {
  const res = await page.evaluate(async () => {
    const r = await fetch("/api/forex/stream-url");
    return { status: r.status, body: (await r.json()) as { url: string } };
  });
  expect(res.status).toBe(200);
  const url = new URL(res.body.url);
  expect(["ws:", "wss:"]).toContain(url.protocol);
  expect(url.search).toBe("");
  expect(url.username + url.password).toBe("");
  const anonymous = await (
    await browser.newContext()
  ).request.get(new URL("/api/forex/stream-url", page.url()).toString());
  expect(anonymous.status()).toBe(401);
});

test("with the module off there is no entry, no page and no ticket", async () => {
  test.skip(FOREX_ON, "forex is on in this stack");
  await page.goto("/home");
  await hydrated(page);
  await expect(
    page
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Live markets" }),
  ).toHaveCount(0);
  await page.goto("/forex");
  await expect(page).toHaveURL(/\/home$/);
  expect(
    (await api(page, "forex/stream-ticket", { method: "POST", body: {} }))
      .status,
  ).toBe(404);
});

test("with the module on the page connects with a ticket and shows labelled quotes", async () => {
  test.skip(!FOREX_ON, "needs an API with forex on (WS_E2E_FOREX=1)");
  await page.goto("/forex");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Live markets" }),
  ).toBeVisible();
  await expect(page.getByRole("status")).toContainText(
    "Live quotes connected",
    { timeout: 30_000 },
  );
  await expect(page.getByRole("table", { name: "Live quotes" })).toBeVisible();
  await expect(
    page.getByText("places no trades", { exact: false }).first(),
  ).toBeVisible();
  await settled(page);
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(
    results.violations
      .filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => v.id),
  ).toEqual([]);
});
