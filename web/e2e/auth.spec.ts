import { expect, test, type Browser, type Page } from "@playwright/test";

import { signIn } from "./helpers";

/**
 * Sign-in and sessions through the BFF against the real stack (P14-T05): Keycloak (the development
 * realm), the API with real token verification, Redis and PostgreSQL. Runs when WS_E2E_AUTH=1 (CI,
 * or locally after `docker compose up` and `python scripts/keycloak_dev.py seed-users web-client`);
 * WS_E2E_PASSWORD is the seeded test users' password.
 */
const ENABLED = process.env.WS_E2E_AUTH === "1";
test.skip(!ENABLED, "needs the full stack (WS_E2E_AUTH=1)");
test.describe.configure({ mode: "serial" });

async function api(page: Page, path: string, init: { method?: string; body?: unknown; csrf?: boolean } = {}) {
  return page.evaluate(
    async ({ path, init }) => {
      const csrf = document.cookie.match(/(?:^|; )__Host-ws_csrf=([^;]+)/)?.[1];
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (init.csrf && csrf) headers["x-csrf-token"] = decodeURIComponent(csrf);
      const r = await fetch(`/api/proxy/${path}`, {
        method: init.method ?? "GET",
        headers,
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
      });
      return { status: r.status, body: await r.json().catch(() => null) };
    },
    { path, init },
  );
}

async function newPage(browser: Browser): Promise<Page> {
  return (await browser.newContext()).newPage();
}

let alicePortfolio = "";

test("Alice signs in through Keycloak; no token is visible to the browser", async ({ page, context }) => {
  await signIn(page, "alice@example.test");
  // Cookies the portal's pages receive (Keycloak's own cookies are scoped to its /realms paths).
  const cookies = await context.cookies(new URL("/", page.url()).href);
  const session = cookies.find((c) => c.name === "__Host-ws_session");
  expect(session).toMatchObject({ httpOnly: true, secure: true, sameSite: "Lax", path: "/" });
  for (const c of cookies) expect(c.value).not.toMatch(/^eyJ/); // no JWT in any cookie
  const visible = await page.evaluate(() => [document.cookie, JSON.stringify(localStorage), JSON.stringify(sessionStorage)].join("|"));
  expect(visible).not.toContain("ws_session");
  expect(visible).not.toMatch(/eyJ[\w-]+\.[\w-]+/);

  const me = await api(page, "me");
  expect(me.status).toBe(200);
  expect(JSON.stringify(me.body)).toContain("alice@example.test");
  expect(JSON.stringify(me.body)).not.toMatch(/eyJ[\w-]+\.[\w-]+/);
});

test("state-changing calls need the CSRF token; with it, Alice creates a portfolio", async ({ browser }) => {
  const page = await newPage(browser);
  await signIn(page, "alice@example.test");
  const body = { name: `Web e2e ${Date.now()}`, base_currency: "USD" };
  expect((await api(page, "portfolios", { method: "POST", body })).status).toBe(403);
  const created = await api(page, "portfolios", { method: "POST", body, csrf: true });
  expect(created.status, JSON.stringify(created.body)).toBe(201);
  alicePortfolio = created.body.id;
});

test("Bob cannot read Alice's portfolio through the BFF", async ({ browser }) => {
  test.skip(!alicePortfolio, "needs the portfolio from the previous test");
  const page = await newPage(browser);
  await signIn(page, "bob@example.test");
  expect((await api(page, `portfolios/${alicePortfolio}`)).status).toBe(404);
  const list = await api(page, "portfolios");
  expect(list.status).toBe(200);
  expect(JSON.stringify(list.body)).not.toContain(alicePortfolio);
});

test("signing out ends the session everywhere: the old cookie no longer works", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await signIn(page, "alice@example.test");
  const stolen = (await context.cookies()).find((c) => c.name === "__Host-ws_session")!;
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  expect((await api(page, "me")).status).toBe(401);

  const replay = await browser.newContext();
  await replay.addCookies([stolen]);
  const replayPage = await replay.newPage();
  await replayPage.goto("/");
  expect((await api(replayPage, "me")).status).toBe(401);
  expect(await replayPage.evaluate(async () => (await (await fetch("/api/auth/session")).json()).signedIn)).toBe(false);
});

test("MFA: a user who must enrol TOTP does so at Keycloak before the portal signs them in", async ({ browser }) => {
  const page = await newPage(browser);
  await signIn(page, "mfa@example.test");
  expect((await api(page, "me")).status).toBe(200);
});
