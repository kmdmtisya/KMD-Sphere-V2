import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * Profile, settings, alerts, watchlist and notifications (P14-T16), signed in against the real
 * stack. Needs WS_E2E_AUTH=1. Saved values are compared with the API's response.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
let page: Page;
let portfolioId = "";
let alertId = "";

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
  const created = await api(page, "portfolios", {
    method: "POST",
    body: { name: `Alerts ${TAG}`, base_currency: "USD" },
  });
  expect(created.status).toBe(201);
  portfolioId = created.body.id;
});

test("the profile is saved to the account and read back", async () => {
  await page.goto("/settings");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Settings" }),
  ).toBeVisible();
  const before = (await api(page, "me")).body;
  const name = `Alice ${TAG}`;
  const card = page.getByRole("region", { name: /^Profile/ });
  await expect(card.getByLabel("Display name")).toBeVisible({
    timeout: 15_000,
  });
  await card.getByLabel("Display name").fill(name);
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect(card.getByRole("status")).toHaveText("Saved.");
  expect((await api(page, "me")).body.display_name).toBe(name);
  // A bad country code is explained and nothing is sent.
  await card.getByLabel("Country of residence").fill("A1");
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect(
    card.getByText("Use a two-letter country code such as AE or US."),
  ).toBeVisible();
  // Put the name back.
  await card
    .getByLabel("Country of residence")
    .fill(before.residence_country ?? "");
  await card.getByLabel("Display name").fill(before.display_name ?? "Alice");
  await card.getByRole("button", { name: "Save changes" }).click();
  await expect
    .poll(async () => (await api(page, "me")).body.display_name)
    .toBe(before.display_name ?? "Alice");
});

test("a risk assessment is recorded to the account", async () => {
  await page.goto("/settings");
  await hydrated(page);
  const card = page.getByRole("region", { name: /^Risk profile/ });
  await expect(card.getByRole("radio", { name: /Growth/ })).toBeVisible({
    timeout: 15_000,
  });
  await card.getByRole("radio", { name: /Growth/ }).check();
  await card.getByLabel("Investment horizon, in years (optional)").fill("12");
  await card.getByRole("button", { name: /Record/ }).click();
  await expect(card.getByRole("status")).toHaveText("Recorded.");
  const latest = (
    (await api(page, "risk-profiles")).body as {
      risk_tolerance: string;
      horizon_years: number;
    }[]
  )[0];
  expect(latest.risk_tolerance).toBe("growth");
  expect(latest.horizon_years).toBe(12);
  await card.getByLabel("Investment horizon, in years (optional)").fill("101");
  await expect(
    card.getByText("Enter whole years from 0 to 100."),
  ).toBeVisible();
  await expect(card.getByRole("button", { name: /Record/ })).toBeDisabled();
});

test("security shows the session and the identity provider link, and holds no token", async () => {
  await expect(
    page.getByRole("link", { name: /Change password or manage multi-factor/ }),
  ).toHaveAttribute("href", /\/account$/);
  await expect(
    page.getByRole("button", { name: "Sign out of this browser" }),
  ).toBeVisible();
  const stored = await page.evaluate(
    () =>
      JSON.stringify({ ...localStorage }) +
      JSON.stringify({ ...sessionStorage }),
  );
  expect(stored).not.toMatch(/eyJ[A-Za-z0-9_-]{10,}/); // no JWT in browser storage
});

test("a registered mobile device is listed and can be removed", async () => {
  const token = `e2e-token-${TAG}-${"x".repeat(40)}`;
  const registered = await api(page, "devices", {
    method: "POST",
    body: { platform: "android", token },
  });
  expect(registered.status, JSON.stringify(registered.body)).toBeLessThan(300);
  await page.goto("/settings");
  await hydrated(page);
  const card = page.getByRole("region", { name: /^Mobile devices/ });
  await expect(
    card.getByRole("table", { name: "Registered mobile devices" }),
  ).toBeVisible({ timeout: 15_000 });
  await card
    .getByRole("button", { name: /^Remove/ })
    .first()
    .click();
  await expect
    .poll(async () => ((await api(page, "devices")).body as unknown[]).length)
    .toBe(0);
});

test("create, pause, resume and delete an allocation alert", async () => {
  await page.goto("/alerts");
  await hydrated(page);
  await page
    .getByRole("radio", { name: "Alerts", exact: true })
    .check({ force: true });
  await page.getByRole("button", { name: "New alert" }).click();
  const drawer = page.getByRole("dialog", { name: "New alert" });
  await drawer.getByLabel("Alert me when").selectOption("allocation_above");
  await drawer.getByRole("button", { name: "Create the alert" }).click();
  await expect(drawer.getByText("Choose the portfolio.")).toBeVisible();
  await drawer
    .getByLabel("Portfolio", { exact: true })
    .selectOption(portfolioId);
  await drawer.getByLabel("Asset class").selectOption({ index: 1 });
  await drawer.getByLabel("Share of the portfolio (%)").fill("40");
  await drawer.getByRole("button", { name: "Create the alert" }).click();
  await expect(drawer).toBeHidden();
  const list = (await api(page, "alerts")).body as {
    id: string;
    status: string;
    portfolio_id: string;
  }[];
  const mine = list.find((a) => a.portfolio_id === portfolioId);
  expect(mine).toBeTruthy();
  alertId = mine!.id;
  await page
    .getByRole("button", { name: /^Pause/ })
    .first()
    .click();
  await expect
    .poll(
      async () =>
        ((await api(page, `alerts/${alertId}`)).body as { status: string })
          .status,
    )
    .toBe("paused");
  await page
    .getByRole("button", { name: /^Resume/ })
    .first()
    .click();
  await expect
    .poll(
      async () =>
        ((await api(page, `alerts/${alertId}`)).body as { status: string })
          .status,
    )
    .toBe("active");
  await page
    .getByRole("button", { name: /^Delete/ })
    .first()
    .click();
  await expect
    .poll(async () => (await api(page, `alerts/${alertId}`)).status)
    .toBe(404);
});

test("the watchlist adds and removes an asset, and the notification centre starts empty", async () => {
  const name = `Watch ${TAG}`;
  const asset = await api(page, "assets", {
    method: "POST",
    body: { asset_class: "real_estate", name, currency: "USD" },
  });
  expect(asset.status, JSON.stringify(asset.body)).toBe(201);
  await page.goto("/alerts");
  await hydrated(page);
  await expect(page.getByText("No alert has been triggered yet.")).toBeVisible({
    timeout: 15_000,
  });
  await page
    .getByRole("radio", { name: "Watchlist", exact: true })
    .check({ force: true });
  await page.getByLabel("Add an asset", { exact: true }).fill(name);
  await page
    .getByRole("list", { name: "Matching assets" })
    .getByRole("button", { name: new RegExp(name) })
    .click();
  await page.getByRole("button", { name: "Add to watchlist" }).click();
  await expect(
    page
      .getByRole("listitem")
      .filter({ hasText: name })
      .filter({ hasText: "No price recorded yet" }),
  ).toBeVisible({ timeout: 15_000 });
  await page
    .getByRole("button", { name: new RegExp(`^Remove ${name}`) })
    .click();
  await expect(
    page
      .getByRole("listitem")
      .filter({ hasText: name })
      .filter({ hasText: "No price recorded yet" }),
  ).toHaveCount(0);
});

test("another user cannot see or change this user's alerts or watchlist", async ({
  browser,
}) => {
  const mine = await api(page, "alerts", {
    method: "POST",
    body: {
      alert_type: "allocation_above",
      portfolio_id: portfolioId,
      asset_class: "real_estate",
      threshold_percent: "50",
    },
  });
  expect(mine.status, JSON.stringify(mine.body)).toBe(201);
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  expect((await api(bob, `alerts/${mine.body.id}`)).status).toBe(404);
  expect(
    (await api(bob, `alerts/${mine.body.id}`, { method: "DELETE" })).status,
  ).toBe(404);
  expect(
    ((await api(bob, "alerts")).body as { id: string }[]).some(
      (a) => a.id === mine.body.id,
    ),
  ).toBe(false);
  await api(page, `alerts/${mine.body.id}`, { method: "DELETE" });
});

test("settings and alerts pass axe in Light and Dark", async () => {
  for (const path of ["/settings", "/alerts"]) {
    await page.goto(path);
    await hydrated(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
      timeout: 20_000,
    });
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
      expect(
        serious.map((x) => `${path} ${mode}: ${x.id} (${x.nodes.length})`),
      ).toEqual([]);
    }
  }
});
