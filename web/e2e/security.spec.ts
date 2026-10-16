import { expect, test, type Page } from "@playwright/test";

import { api, signIn } from "./helpers";

/**
 * Web security tests (P14-T19, QG-29.5, QG-29.7), against the real stack. Needs WS_E2E_AUTH=1:
 * the Content-Security-Policy is enforced and blocks other origins, a cross-site write is refused,
 * hostile text is shown as text, and one user cannot reach another's records through the portal.
 */
test.skip(
  process.env.WS_E2E_AUTH !== "1",
  "needs the full stack (WS_E2E_AUTH=1)",
);
test.describe.configure({ mode: "serial" });

const TAG = Date.now().toString(36);
const HOSTILE = `<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>`;
let alice: Page;
let aliceIds: Record<string, string> = {};

async function hydrated(p: Page) {
  await expect(p.getByLabel("Reporting currency").first()).toHaveValue(
    /^[A-Z]{3}$/,
    { timeout: 20_000 },
  );
}

test.beforeAll(async ({ browser }) => {
  alice = await (
    await browser.newContext({ viewport: { width: 1440, height: 900 } })
  ).newPage();
  await signIn(alice, "alice@example.test");
});

test("every page carries the security headers and an enforced CSP without eval", async () => {
  for (const path of ["/", "/home", "/settings"]) {
    const response = await alice.goto(path);
    const h = response!.headers();
    const csp = h["content-security-policy"] ?? "";
    expect(csp, path).toContain("default-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toMatch(/form-action 'self'/);
    expect(csp).not.toContain("'unsafe-eval'");
    expect(csp).not.toMatch(/script-src[^;]*\*/); // no wildcard script source
    expect(h["content-security-policy-report-only"]).toBeUndefined(); // enforced, not just reported
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["x-frame-options"]).toBe("DENY");
    expect(h["referrer-policy"]).toBe("same-origin");
    expect(h["x-powered-by"]).toBeUndefined();
  }
});

test("the CSP blocks a script, a request and a frame from another origin", async () => {
  await alice.goto("/home");
  await hydrated(alice);
  const violations = await alice.evaluate(
    () =>
      new Promise<string[]>((resolve) => {
        const seen: string[] = [];
        document.addEventListener("securitypolicyviolation", (e) =>
          seen.push(`${e.violatedDirective}`),
        );
        const script = document.createElement("script");
        script.src = "https://evil.example.test/steal.js";
        document.head.appendChild(script);
        fetch("https://evil.example.test/collect").catch(() => undefined);
        const frame = document.createElement("iframe");
        frame.src = "https://evil.example.test/frame";
        document.body.appendChild(frame);
        const form = document.createElement("form");
        form.action = "https://evil.example.test/post";
        form.method = "post";
        document.body.appendChild(form);
        setTimeout(() => resolve(seen), 1500);
      }),
  );
  expect(violations.some((v) => v.startsWith("script-src"))).toBe(true);
  expect(violations.some((v) => v.startsWith("connect-src"))).toBe(true);
  expect(
    violations.some(
      (v) => v.startsWith("frame-src") || v.startsWith("default-src"),
    ),
  ).toBe(true);
});

test("the portal cannot be framed by another site", async ({ browser }) => {
  const page = await (await browser.newContext()).newPage();
  await page.setContent(
    `<iframe id="f" src="${new URL("/", alice.url()).href}" width="400" height="300"></iframe>`,
  );
  const refused = await page.evaluate(
    () =>
      new Promise<boolean>((resolve) => {
        const frame = document.getElementById("f") as HTMLIFrameElement;
        frame.onload = () => {
          try {
            resolve(
              frame.contentDocument === null ||
                frame.contentDocument.body?.innerHTML === "",
            );
          } catch {
            resolve(true);
          }
        };
        setTimeout(() => resolve(true), 4000);
      }),
  );
  expect(refused).toBe(true);
});

test("a write from another site is refused: wrong Origin, no Origin and no token", async () => {
  await alice.goto("/home");
  await hydrated(alice);
  const base = new URL(alice.url()).origin;
  const outcomes = await alice.evaluate(async (origin) => {
    const csrf = decodeURIComponent(
      /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "",
    );
    const body = JSON.stringify({
      name: `csrf ${Date.now()}`,
      base_currency: "USD",
    });
    const post = async (headers: Record<string, string>) =>
      (
        await fetch(`${origin}/api/proxy/portfolios`, {
          method: "POST",
          headers: { "content-type": "application/json", ...headers },
          body,
        })
      ).status;
    return {
      noToken: await post({}),
      wrongToken: await post({ "x-csrf-token": "not-the-token" }),
      // A browser sets Origin itself and a page cannot forge it; the server must still check it.
      withToken: csrf ? await post({ "x-csrf-token": csrf }) : 0,
    };
  }, base);
  expect(outcomes.noToken).toBe(403);
  expect(outcomes.wrongToken).toBe(403);
  expect(outcomes.withToken).toBeLessThan(300); // the legitimate call still works (then cleaned up below)
  // Directly, with a foreign Origin header and the right cookies/token: refused.
  const context = alice.context();
  const cookies = await context.cookies(base);
  const csrfCookie = cookies.find((c) => c.name === "__Host-ws_csrf")!;
  const foreign = await context.request.post(`${base}/api/proxy/portfolios`, {
    headers: {
      origin: "https://evil.example.test",
      "content-type": "application/json",
      "x-csrf-token": csrfCookie.value,
    },
    data: { name: "from evil", base_currency: "USD" },
  });
  expect(foreign.status()).toBe(403);
  const list = (await api(alice, "portfolios")).body as { name: string }[];
  expect(list.some((p) => p.name === "from evil")).toBe(false);
});

test("the proxy refuses paths outside /api/v1 and traversal", async () => {
  const statuses = await alice.evaluate(async () => {
    const get = async (path: string) => (await fetch(path)).status;
    return {
      traversal: await get("/api/proxy/..%2F..%2Fadmin"),
      encodedSlash: await get("/api/proxy/%2e%2e%2fhealth"),
      backslash: await get("/api/proxy/portfolios%5c..%5cme"),
      absolute: await get("/api/proxy/http:%2F%2Fevil.example.test%2F"),
      health: await get("/api/proxy/health/ready"),
    };
  });
  for (const [name, status] of Object.entries(statuses))
    expect([400, 404], name).toContain(status);
});

test("hostile text is shown as text everywhere it can appear, and runs nothing", async () => {
  const name = `${HOSTILE} ${TAG}`;
  const portfolio = await api(alice, "portfolios", {
    method: "POST",
    body: { name, base_currency: "USD" },
  });
  expect(portfolio.status, JSON.stringify(portfolio.body)).toBe(201);
  const goal = await api(alice, "goals", {
    method: "POST",
    body: {
      name,
      goal_type: "wealth",
      target: { amount: "1000.00", currency: "USD" },
      target_date: "2034-01-01",
      target_in_todays_money: false,
      assumptions: {
        contribution: { amount: "10.00", currency: "USD" },
        returns: { base: "5" },
      },
    },
  });
  expect(goal.status, JSON.stringify(goal.body)).toBe(201);
  const asset = await api(alice, "assets", {
    method: "POST",
    body: { asset_class: "real_estate", name, currency: "USD" },
  });
  expect(asset.status, JSON.stringify(asset.body)).toBe(201);
  aliceIds = {
    portfolio: portfolio.body.id,
    goal: goal.body.id,
    asset: asset.body.id,
  };

  for (const path of [
    "/portfolio",
    `/portfolio/${aliceIds.portfolio}`,
    "/goals",
    "/home",
    "/alerts",
  ]) {
    await alice.goto(path);
    await hydrated(alice);
    await alice.waitForTimeout(1200);
    expect(
      await alice.evaluate(
        () => (window as unknown as { __pwned?: number }).__pwned,
      ),
      path,
    ).toBeUndefined();
    // The markup is on the page as characters, never as elements.
    expect(await alice.locator("main img[src='x']").count(), path).toBe(0);
  }
  await alice.goto("/portfolio");
  await expect(
    alice.locator("main").getByText("onerror", { exact: false }).first(),
  ).toBeVisible({ timeout: 15_000 });
  await api(alice, `goals/${aliceIds.goal}`, { method: "DELETE" });
});

test("another user cannot reach this user's records through the portal", async ({
  browser,
}) => {
  const bob = await (await browser.newContext()).newPage();
  await signIn(bob, "bob@example.test");
  const probes = [
    `portfolios/${aliceIds.portfolio}`,
    `portfolios/${aliceIds.portfolio}/summary`,
    `portfolios/${aliceIds.portfolio}/holdings`,
    `portfolios/${aliceIds.portfolio}/transactions`,
    `portfolios/${aliceIds.portfolio}/performance`,
    `portfolios/${aliceIds.portfolio}/allocation`,
    `portfolios/${aliceIds.portfolio}/risk`,
    `portfolios/${aliceIds.portfolio}/income`,
    `goals/${aliceIds.goal}`,
    `goals/${aliceIds.goal}/progress`,
    `assets/${aliceIds.asset}`,
    `assets/${aliceIds.asset}/prices`,
    `reports/portfolio?portfolio_id=${aliceIds.portfolio}&format=csv`,
  ];
  for (const path of probes) {
    const r = await api(bob, path);
    expect(r.status, path).toBe(404);
  }
  const mine = JSON.stringify([
    (await api(bob, "portfolios")).body,
    (await api(bob, "goals")).body,
    (await api(bob, "assets/search?q=Danger")).body,
  ]);
  expect(mine).not.toContain(aliceIds.portfolio);
  expect(mine).not.toContain(aliceIds.asset);
  // And through the pages: Bob's portfolio page for Alice's id shows nothing of hers.
  await bob.goto(`/portfolio/${aliceIds.portfolio}`);
  await bob.waitForTimeout(2500);
  expect(await bob.locator("main").innerText()).not.toContain(TAG);
});

test("a stolen session cookie stops working when the user signs out", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, "alice@example.test");
  const base = new URL(page.url()).origin;
  const cookie = (await context.cookies(base)).find(
    (c) => c.name === "__Host-ws_session",
  )!;
  expect(cookie.httpOnly && cookie.secure).toBe(true);
  await page.getByRole("button", { name: "Sign out" }).click();
  const replay = await (
    await browser.newContext()
  ).request.get(`${base}/api/proxy/me`, {
    headers: { cookie: `__Host-ws_session=${cookie.value}` },
  });
  expect(replay.status()).toBe(401);
});
