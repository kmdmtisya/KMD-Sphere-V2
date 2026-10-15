import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, settled, signIn } from "./helpers";

/**
 * The AI Copilot and investment intelligence (P14-T12), signed in against the real stack. Needs
 * WS_E2E_AUTH=1. The test stack configures no assistant, so the journeys that need no model are
 * exercised end to end: the "assistant unavailable" path, the Doctor's deterministic checks, the universe, research and
 * comparison. Streamed-answer rendering is covered by unit tests of the parser.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
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
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(page, "alice@example.test");
  const created = await api(page, "portfolios", {
    method: "POST",
    body: { name: `AI ${TAG}`, base_currency: "USD" },
  });
  expect(created.status).toBe(201);
  portfolioId = created.body.id;
  const deposit = await api(page, `portfolios/${portfolioId}/transactions`, {
    method: "POST",
    body: {
      transaction_type: "DEPOSIT",
      trade_date: "2026-01-05",
      currency: "USD",
      gross_amount: { amount: "5000.00", currency: "USD" },
    },
  });
  expect(deposit.status).toBe(201);
});

test("when no assistant is configured the page says so plainly and stays usable", async () => {
  await page.goto("/ai");
  await hydrated(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Copilot" }),
  ).toBeVisible();
  await page.getByLabel("Ask a question").fill("How is my portfolio doing?");
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByRole("article", {
    name: /Question: How is my portfolio doing/,
  });
  await expect(answer.getByRole("alert")).toHaveText(
    "The assistant is unavailable right now. Please try again shortly.",
    { timeout: 30_000 },
  );
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled(); // the draft is empty again
  await page.getByLabel("Ask a question").fill("Another question");
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
});

const sse = (events: object[]) =>
  events
    .map(
      (e) => `event: ${(e as { type: string }).type}
data: ${JSON.stringify(e)}

`,
    )
    .join("");

test("a streamed answer shows its checks, its sources and its four parts apart", async () => {
  await page.route("**/api/proxy/ai/chat", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        { type: "tool", name: "get_net_worth", status: "running" },
        { type: "tool", name: "get_net_worth", status: "ok" },
        {
          type: "source",
          tool: "get_net_worth",
          as_of: "2026-10-15T10:00:00Z",
          complete: true,
        },
        { type: "token", text: "Your net worth is shown below." },
        {
          type: "done",
          conversation_id: "11111111-1111-4111-8111-111111111111",
          message_id: "22222222-2222-4222-8222-222222222222",
          model: "m",
          provider: "p",
          tool_calls: 1,
          structured: {
            observed: [{ text: "Assets are 5,000.", source: "get_net_worth" }],
            calculated: [
              { text: "Net worth is 5,000.", source: "get_net_worth" },
            ],
            assumptions: ["Values are at today's rates."],
            interpretation: "You hold only cash.",
            caveats: ["Not personal investment advice."],
          },
        },
      ]),
    }),
  );
  await page.goto("/ai");
  await hydrated(page);
  await page.getByLabel("Ask a question").fill("What is my net worth?");
  await page.getByRole("button", { name: "Send" }).click();
  const answer = page.getByRole("article", {
    name: /Question: What is my net worth/,
  });
  await expect(
    answer.getByRole("heading", { name: "What your data shows" }),
  ).toBeVisible();
  await expect(
    answer.getByRole("heading", { name: "Calculated by WealthSphere" }),
  ).toBeVisible();
  await expect(
    answer.getByRole("heading", { name: "Assumptions" }),
  ).toBeVisible();
  await expect(
    answer.getByRole("heading", { name: "AI interpretation" }),
  ).toBeVisible();
  await expect(answer.getByText("Assets are 5,000.")).toBeVisible();
  await expect(answer.getByRole("list", { name: "Checks made" })).toContainText(
    "net worth: done",
  );
  await expect(
    answer.getByRole("list", { name: "Data this answer rests on" }),
  ).toBeVisible();
  await page.unroute("**/api/proxy/ai/chat");
});

test("a refusal is shown in plain words and the answer text is never rendered as HTML", async () => {
  await page.route("**/api/proxy/ai/chat", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        {
          type: "done",
          conversation_id: "11111111-1111-4111-8111-111111111111",
          message_id: "22222222-2222-4222-8222-222222222222",
          model: "m",
          provider: "p",
          tool_calls: 0,
          structured: { refusal: "trade_execution" },
        },
      ]),
    }),
  );
  await page.goto("/ai");
  await hydrated(page);
  await page.getByLabel("Ask a question").fill("Sell everything now");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(
    page.getByText("does not place trades or move money"),
  ).toBeVisible();
  await page.unroute("**/api/proxy/ai/chat");

  await page.route("**/api/proxy/ai/chat", (route) =>
    route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sse([
        {
          type: "done",
          conversation_id: "11111111-1111-4111-8111-111111111111",
          message_id: "22222222-2222-4222-8222-222222222222",
          model: "m",
          provider: "p",
          tool_calls: 0,
          structured: {
            interpretation: "<img src=x onerror=window.__xss=1> <b>bold</b>",
          },
        },
      ]),
    }),
  );
  await page.getByLabel("Ask a question").fill("Show me markup");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("<b>bold</b>", { exact: false })).toBeVisible();
  expect(
    await page.evaluate(() => (window as unknown as { __xss?: number }).__xss),
  ).toBeUndefined();
  await page.unroute("**/api/proxy/ai/chat");
});

test("the docked panel is scoped to the portfolio being viewed", async () => {
  await page.goto(`/portfolio/${portfolioId}`);
  await hydrated(page);
  await page.keyboard.press("Control+j");
  const panel = page.getByRole("complementary", { name: "Copilot" });
  await expect(panel.getByText("this portfolio is in scope")).toBeVisible();
  await page.keyboard.press("Escape");
});

test("the Doctor checks a portfolio with the API's findings and no instruction to trade", async () => {
  await page.goto("/ai/doctor");
  await hydrated(page);
  await page.getByLabel("Portfolio", { exact: true }).selectOption(portfolioId);
  await page
    .getByRole("button", { name: /Check this portfolio|Check again/ })
    .click();
  const expected = (
    await api(page, "ai/portfolio-doctor", {
      method: "POST",
      body: { portfolio_id: portfolioId },
    })
  ).body;
  await expect(page.getByRole("region", { name: /^Overall/ })).toBeVisible({
    timeout: 30_000,
  });
  await expect(page.getByRole("region", { name: /^Findings/ })).toBeVisible();
  await expect(page.getByText("About the Doctor")).toBeVisible();
  expect(expected.findings.length).toBeGreaterThan(0);
  await expect(
    page.getByRole("region", { name: /^Findings/ }).getByRole("listitem"),
  ).toHaveCount(expected.findings.length);
});

test("the universe and the research library load, with DEMO data labelled", async () => {
  await page.goto("/ai/opportunities");
  await hydrated(page);
  await expect(
    page.getByText("Nothing here is personal investment advice"),
  ).toBeVisible();
  await page
    .getByRole("radio", { name: "Universe", exact: true })
    .check({ force: true });
  const universe = (await api(page, "universe?eligible_only=false")).body;
  if (universe.total === 0)
    await expect(
      page.getByText("No instrument matches these filters."),
    ).toBeVisible();
  else
    await expect(
      page.getByRole("region", {
        name: new RegExp(`^${universe.eligible} of ${universe.total} eligible`),
      }),
    ).toBeVisible();
  await page
    .getByRole("radio", { name: "Research", exact: true })
    .check({ force: true });
  await expect(page.getByLabel("Search the research library")).toBeVisible();
});

test("two instruments compare side by side", async () => {
  const universe = (await api(page, "universe?eligible_only=false")).body as {
    items: { name: string }[];
  };
  test.skip(
    universe.items.length < 2,
    "the universe has fewer than two instruments",
  );
  await page.goto("/ai/opportunities/compare");
  await hydrated(page);
  const boxes = page
    .getByRole("group", { name: "Instruments to compare" })
    .getByRole("checkbox");
  await boxes.nth(0).check();
  await boxes.nth(1).check();
  await page.getByRole("button", { name: /Compare/ }).click();
  await expect(
    page.getByRole("table", { name: "Instruments compared" }),
  ).toBeVisible({ timeout: 20_000 });
  await expect(
    page.getByRole("rowheader", { name: /Past price change/ }),
  ).toBeVisible();
});

test("another user cannot run the Doctor on this portfolio or read these conversations", async ({
  browser,
}) => {
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  expect(
    (
      await api(bob, "ai/portfolio-doctor", {
        method: "POST",
        body: { portfolio_id: portfolioId },
      })
    ).status,
  ).toBe(404);
  const mine = (await api(page, "ai/conversations")).body as { id: string }[];
  for (const c of mine.slice(0, 3))
    expect((await api(bob, `ai/conversations/${c.id}`)).status).toBe(404);
});

test("the AI pages pass axe in Light and Dark", async () => {
  for (const path of [
    "/ai",
    "/ai/doctor",
    "/ai/opportunities",
    "/ai/opportunities/compare",
  ]) {
    await page.goto(path);
    await hydrated(page);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible({
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
      expect(
        serious.map((x) => `${path} ${mode}: ${x.id} (${x.nodes.length})`),
      ).toEqual([]);
    }
  }
});
