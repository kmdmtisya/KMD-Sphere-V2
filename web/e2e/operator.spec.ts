import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * Operator views (P14-T17, DEC-34), signed in against the real stack. Needs WS_E2E_AUTH=1. The
 * demo operator `ops@example.test` holds the `support` realm role; nobody else does. The control is
 * the API: the menu entry and page are hidden for everyone else, and the API answers 403 anyway.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

let user: Page;
let ops: Page;

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

test.beforeAll(async ({ browser }) => {
  user = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(user, "alice@example.test");
  ops = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(ops, "ops@example.test");
});

test("a normal user has no entry and no page, and the API refuses them anyway", async () => {
  await user.goto("/home");
  await hydrated(user);
  await expect(
    user
      .getByRole("navigation", { name: "Main" })
      .getByRole("link", { name: "Operator views" }),
  ).toHaveCount(0);
  await user.goto("/operator");
  await expect(user).toHaveURL(/\/home$/);
  for (const path of ["operator/status", "operator/audit"]) {
    expect((await api(user, path)).status).toBe(403);
  }
});

test("the operator sees platform status and audit activity, never an account's data", async () => {
  await ops.goto("/home");
  await hydrated(ops);
  await ops
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Operator views" })
    .click();
  await expect(ops).toHaveURL(/\/operator$/);
  await expect(
    ops.getByRole("heading", { level: 1, name: "Operator views" }),
  ).toBeVisible();
  await expect(ops.getByRole("region", { name: /^Dependencies/ })).toBeVisible({
    timeout: 20_000,
  });
  const status = (await api(ops, "operator/status")).body;
  await expect(ops.getByRole("region", { name: /^Accounts/ })).toContainText(
    String(status.users.active),
  );
  await expect(
    ops.getByRole("table", { name: "Audit events", exact: true }),
  ).toBeVisible({
    timeout: 20_000,
  });
  const text = await ops.locator("main").innerText();
  expect(text).not.toContain("@example.test");
  expect(text).not.toMatch(
    /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/,
  ); // no ids
});

test("the refused attempt of the normal user is in the audit trail", async () => {
  const items = (
    await api(ops, "operator/audit?outcome=denied&action_prefix=operator.")
  ).body as { action: string }[];
  expect(items.some((i) => i.action === "operator.access.denied")).toBe(true);
  await ops.goto("/operator");
  await ops.getByLabel("Outcome").selectOption("denied");
  await expect(
    ops
      .getByRole("table", { name: "Audit events", exact: true })
      .getByRole("cell", { name: "operator.access.denied" })
      .first(),
  ).toBeVisible();
});

test("the operator pages pass axe in Light and Dark", async () => {
  await ops.goto("/operator");
  await hydrated(ops);
  await expect(
    ops.getByRole("table", { name: "Audit events", exact: true }),
  ).toBeVisible({
    timeout: 20_000,
  });
  for (const mode of ["light", "dark"] as const) {
    await ops.evaluate(
      (m) => document.documentElement.setAttribute("data-theme-pref", m),
      mode,
    );
    await settled(ops);
    const results = await new AxeBuilder({ page: ops })
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
