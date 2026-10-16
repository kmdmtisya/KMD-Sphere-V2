import { expect, test, type Browser, type Page } from "@playwright/test";

import { api, signIn } from "./helpers";

/**
 * One user, every channel (P14-T18, QG-26.4, QG-33.7), against the real stack. Needs
 * WS_E2E_AUTH=1. A record added through the API (as the mobile app does) shows on the web; an edit
 * on the web reads back through the API; and an edit made from a stale version is refused with a
 * prompt to reload, never silently overwritten.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
let first: Page;
let goalId = "";
let liabilityId = "";

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

/** A second browser window for the same user (another device or channel). */
async function secondWindow(browser: Browser): Promise<Page> {
  const page = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
  return page;
}

test.beforeAll(async ({ browser }) => {
  first = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(first, "alice@example.test");
  const goal = await api(first, "goals", {
    method: "POST",
    body: {
      name: `Sync goal ${TAG}`,
      goal_type: "wealth",
      target: { amount: "20000.00", currency: "USD" },
      target_date: "2033-01-01",
      target_in_todays_money: false,
      assumptions: {
        contribution: { amount: "50.00", currency: "USD" },
        returns: { base: "5" },
      },
    },
  });
  expect(goal.status, JSON.stringify(goal.body)).toBe(201);
  goalId = goal.body.id;
  const debt = await api(first, "liabilities", {
    method: "POST",
    body: {
      name: `Sync loan ${TAG}`,
      liability_type: "personal_loan",
      balance: { amount: "900.00", currency: "USD" },
      balance_as_of: "2026-10-01",
    },
  });
  expect(debt.status).toBe(201);
  liabilityId = debt.body.id;
});

test("a goal added through the API shows on the web, and a web edit reads back through the API", async () => {
  await first.goto("/goals");
  await hydrated(first);
  const card = first.getByRole("article", { name: `Sync goal ${TAG}` });
  await expect(card).toBeVisible({ timeout: 15_000 });
  await card.getByRole("button", { name: `Edit Sync goal ${TAG}` }).click();
  const drawer = first.getByRole("dialog", { name: "Edit goal" });
  await drawer.getByLabel(/^Target amount/).fill("25000");
  await drawer.getByRole("button", { name: "Save changes" }).click();
  await expect(drawer).toBeHidden();
  const read = await api(first, `goals/${goalId}`);
  expect(read.body.target.amount).toBe("25000.00");
});

test("an edit from a stale version is refused with a prompt to reload, then succeeds", async ({
  browser,
}) => {
  const second = await secondWindow(browser);
  // Both windows open the same goal for editing.
  for (const page of [first, second]) {
    await page.goto("/goals");
    await hydrated(page);
    await page
      .getByRole("article", { name: `Sync goal ${TAG}` })
      .getByRole("button", { name: `Edit Sync goal ${TAG}` })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Edit goal" }).getByLabel("Name"),
    ).toHaveValue(`Sync goal ${TAG}`);
  }
  // The first window renames it and saves.
  const a = first.getByRole("dialog", { name: "Edit goal" });
  await a
    .getByLabel("Name")
    .fill(`Sync goal ${TAG} (renamed on the first window)`);
  await a.getByRole("button", { name: "Save changes" }).click();
  await expect(a).toBeHidden();
  expect((await api(first, `goals/${goalId}`)).body.name).toContain(
    "renamed on the first window",
  );

  // The second window, still on the old version, tries to save its own change: refused, not overwritten.
  const b = second.getByRole("dialog", { name: "Edit goal" });
  await b.getByLabel(/^Target amount/).fill("30000");
  await b.getByRole("button", { name: "Save changes" }).click();
  await expect(b.getByRole("alert")).toContainText("changed somewhere else");
  const afterRefusal = (await api(first, `goals/${goalId}`)).body;
  expect(afterRefusal.name).toContain("renamed on the first window");
  expect(afterRefusal.target.amount).toBe("25000.00");

  // Loading the latest version shows the other edit; the change can then be made on top of it.
  await b.getByRole("button", { name: "Load the latest version" }).click();
  await expect(b.getByLabel("Name")).toHaveValue(/renamed on the first window/);
  await b.getByLabel(/^Target amount/).fill("30000");
  await b.getByRole("button", { name: "Save changes" }).click();
  await expect(b).toBeHidden();
  const final = (await api(first, `goals/${goalId}`)).body;
  expect(final.name).toContain("renamed on the first window");
  expect(final.target.amount).toBe("30000.00");
});

test("the same holds for a liability", async ({ browser }) => {
  const second = await secondWindow(browser);
  for (const page of [first, second]) {
    await page.goto("/planning/net-worth");
    await hydrated(page);
    await page.getByRole("button", { name: `Edit Sync loan ${TAG}` }).click();
    await expect(
      page.getByRole("dialog", { name: "Edit liability" }).getByLabel("Name"),
    ).toHaveValue(`Sync loan ${TAG}`);
  }
  const a = first.getByRole("dialog", { name: "Edit liability" });
  await a.getByLabel("Balance you owe").fill("800.00");
  await a.getByRole("button", { name: "Save changes" }).click();
  await expect(a).toBeHidden();
  const b = second.getByRole("dialog", { name: "Edit liability" });
  await b.getByLabel("Balance you owe").fill("700.00");
  await b.getByRole("button", { name: "Save changes" }).click();
  await expect(b.getByRole("alert")).toContainText("changed somewhere else");
  expect(
    (await api(first, `liabilities/${liabilityId}`)).body.balance.amount,
  ).toBe("800.00");
});

test("the API gives every editable record a version and refuses a stale one", async () => {
  const read = await first.evaluate(async (id) => {
    const r = await fetch(`/api/proxy/goals/${id}`);
    return { etag: r.headers.get("etag"), status: r.status };
  }, goalId);
  expect(read.etag).toMatch(/^"[0-9a-f]{24}"$/);
  const stale = await first.evaluate(async (id) => {
    const csrf = decodeURIComponent(
      /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "",
    );
    const r = await fetch(`/api/proxy/goals/${id}`, {
      method: "PATCH",
      headers: {
        "content-type": "application/json",
        "x-csrf-token": csrf,
        "if-match": '"0000000000000000000000aa"',
      },
      body: JSON.stringify({ name: "Should not apply" }),
    });
    return r.status;
  }, goalId);
  expect(stale).toBe(409);
});
