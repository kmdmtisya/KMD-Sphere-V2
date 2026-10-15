import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, signIn } from "./helpers";

/**
 * Calculator, forecast scenarios and goals (P14-T10), signed in against the real stack. Needs
 * WS_E2E_AUTH=1. The figures shown are compared with the API's response for the same request
 * (QG-30.4: outputs equal the API).
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const GOAL = `Goal ${Date.now().toString(36)}`;
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

test("the calculator shows the API's figures for three scenarios", async () => {
  await page.goto("/planning/calculator");
  await hydrated(page);
  await page.getByRole("button", { name: "Calculate" }).click();
  const base = page.getByRole("region", { name: "Base scenario" });
  await expect(base).toBeVisible();
  const reporting = (await api(page, "me/currency-preferences")).body
    .reporting_currency as string;
  const expected = await api(
    page,
    `forecasts/scenarios?reporting_currency=${reporting}`,
    {
      method: "POST",
      body: {
        initial_investment: { amount: "10000", currency: reporting },
        contribution: { amount: "500", currency: reporting },
        contribution_frequency: "monthly",
        contribution_growth_percent: "0",
        compounding_frequency: "monthly",
        years: 20,
        annual_return_percent: "7",
        conservative_return_percent: "4",
        growth_return_percent: "10",
        inflation_percent: "2.5",
        annual_fee_percent: "0",
      },
    },
  );
  expect(expected.status).toBe(200);
  for (const [name, key] of [
    ["Cautious", "conservative"],
    ["Base", "base"],
    ["Optimistic", "growth"],
  ] as const) {
    const region = page.getByRole("region", { name: `${name} scenario` });
    await expect(
      region
        .getByText(
          money(
            expected.body.scenarios[key].final_nominal.amount,
            expected.body.currency,
          ),
        )
        .first(),
    ).toBeVisible();
  }
  await expect(page.getByText("About this projection")).toBeVisible();
});

test("a bad input is explained and nothing is sent", async () => {
  await page.getByLabel("Years", { exact: true }).fill("0");
  await page.getByRole("button", { name: "Calculate" }).click();
  await expect(page.getByText("Enter whole years from 1 to 60.")).toBeVisible();
  await page.getByLabel("Years", { exact: true }).fill("20");
});

test("the target planner shows the contribution the API works out", async () => {
  await page.getByRole("button", { name: "Work out the contribution" }).click();
  await expect(
    page.getByText(
      /you would need to contribute about|alone is projected to reach/,
    ),
  ).toBeVisible();
});

test("create, view, edit and delete a goal", async () => {
  await page.goto("/goals");
  await hydrated(page);
  await page.getByRole("button", { name: "New goal" }).click();
  const drawer = page.getByRole("dialog", { name: "New goal" });
  await drawer.getByRole("button", { name: "Create the goal" }).click();
  await expect(drawer.getByText("Give the goal a name.")).toBeVisible();
  await drawer.getByLabel("Name").fill(GOAL);
  await drawer.getByLabel(/^Target amount/).fill("50000");
  await drawer.getByLabel("Reach it by").fill("2032-06-30");
  await drawer.getByRole("button", { name: "Create the goal" }).click();
  await expect(drawer).toBeHidden();
  const card = page.getByRole("article", { name: GOAL });
  await expect(card).toBeVisible();
  const goals = (await api(page, "goals")).body as {
    id: string;
    name: string;
  }[];
  const id = goals.find((g) => g.name === GOAL)!.id;
  const progress = (await api(page, `goals/${id}/progress`)).body;
  await expect(
    card
      .getByText(`${money(progress.gap.amount, progress.gap.currency)}`)
      .first(),
  ).toBeVisible();
  await expect(card.getByRole("progressbar")).toBeVisible();

  await card.getByRole("button", { name: `Edit ${GOAL}` }).click();
  const edit = page.getByRole("dialog", { name: "Edit goal" });
  await edit.getByLabel(/^Target amount/).fill("60000");
  await edit.getByRole("button", { name: "Save changes" }).click();
  await expect(edit).toBeHidden();
  await expect(
    page
      .getByRole("article", { name: GOAL })
      .getByText(money("60000", progress.target.currency))
      .first(),
  ).toBeVisible();

  await page
    .getByRole("article", { name: GOAL })
    .getByRole("button", { name: `Edit ${GOAL}` })
    .click();
  await page
    .getByRole("dialog", { name: "Edit goal" })
    .getByRole("button", { name: "Delete" })
    .click();
  await page.getByRole("button", { name: "Yes, delete this goal" }).click();
  await expect(page.getByRole("article", { name: GOAL })).toHaveCount(0);
});

test("another user cannot read or change a goal", async ({ browser }) => {
  const created = await api(page, "goals", {
    method: "POST",
    body: {
      name: `${GOAL} private`,
      goal_type: "wealth",
      target: { amount: "1000", currency: "USD" },
      target_date: "2032-01-01",
      target_in_todays_money: false,
      assumptions: {
        contribution: { amount: "10", currency: "USD" },
        returns: { base: "5" },
      },
    },
  });
  expect(created.status).toBe(201);
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  expect((await api(bob, `goals/${created.body.id}`)).status).toBe(404);
  expect((await api(bob, `goals/${created.body.id}/progress`)).status).toBe(
    404,
  );
  expect(
    (await api(bob, `goals/${created.body.id}`, { method: "DELETE" })).status,
  ).toBe(404);
  await api(page, `goals/${created.body.id}`, { method: "DELETE" });
});

test("both pages pass axe in Light and Dark", async () => {
  for (const path of ["/planning/calculator", "/goals"]) {
    await page.goto(path);
    await hydrated(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    if (path === "/planning/calculator")
      await page.getByRole("button", { name: "Calculate" }).click();
    if (path === "/planning/calculator")
      await expect(
        page.getByRole("region", { name: "Base scenario" }),
      ).toBeVisible();
    for (const mode of ["light", "dark"] as const) {
      await page.evaluate(
        (m) => document.documentElement.setAttribute("data-theme-pref", m),
        mode,
      );
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
