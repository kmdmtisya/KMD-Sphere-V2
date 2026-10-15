import { createHmac } from "node:crypto";

import { expect, type Page } from "@playwright/test";

/** RFC 6238 code for Keycloak's raw TOTP secret (as scripts/keycloak_dev.py does). */
export function totp(rawSecret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / 30)));
  const digest = createHmac("sha1", Buffer.from(rawSecret)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, "0");
}

/** Milliseconds left in the current 30-second TOTP window. */
function windowLeft(): number {
  return 30_000 - (Date.now() % 30_000);
}

/**
 * Signs in through the portal and Keycloak's own login page. A user who must enrol TOTP does so
 * like a person would: a code from the shown secret, retried once with the next code if the first
 * one crossed a 30-second boundary.
 */
export async function signIn(page: Page, username: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("link", { name: "Sign in" }).click();
  await page.locator("#username").fill(username);
  await page.locator("#password").fill(process.env.WS_E2E_PASSWORD ?? "");
  await page.locator("#kc-login").click();
  const enrol = page.locator('input[name="totpSecret"]');
  // The next page is either the portal (signed in) or Keycloak's TOTP enrolment: wait for one.
  await Promise.race([
    page.getByTestId("signed-in-as").waitFor({ timeout: 15_000 }),
    enrol.waitFor({ state: "attached", timeout: 15_000 }),
  ]).catch(() => undefined);
  for (let attempt = 0; attempt < 2; attempt++) {
    if (!(await enrol.count())) break;
    if (windowLeft() < 5_000) await page.waitForTimeout(windowLeft() + 500);
    await page.locator("#totp").fill(totp(await enrol.inputValue()));
    const label = page.locator("#userLabel");
    if (await label.count()) await label.fill("web e2e");
    await page.locator('input[type="submit"], button[type="submit"]').first().click();
    // Wait for an outcome: back in the portal, or the code marked invalid (then retry once).
    await Promise.race([
      page.getByTestId("signed-in-as").waitFor({ timeout: 15_000 }),
      page.locator('#totp[aria-invalid="true"]').waitFor({ timeout: 15_000 }),
    ]).catch(() => undefined);
  }
  try {
    await expect(page.getByTestId("signed-in-as")).toBeVisible({ timeout: 30_000 });
  } catch (error) {
    const text = (await page.locator("body").innerText().catch(() => "")).replace(/\s+/g, " ").slice(0, 300);
    throw new Error(`sign-in of ${username} did not reach the portal. URL: ${page.url()}. Page: ${text}`, { cause: error });
  }
}

/** Calls the API through the portal's proxy from the page, with the CSRF token for writes. */
export async function api(page: Page, path: string, init: { method?: string; body?: unknown } = {}) {
  return page.evaluate(
    async ({ path, init }) => {
      const csrf = document.cookie.match(/(?:^|; )__Host-ws_csrf=([^;]+)/)?.[1];
      const headers: Record<string, string> = { "content-type": "application/json" };
      if (init.method && init.method !== "GET" && csrf) headers["x-csrf-token"] = decodeURIComponent(csrf);
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

/**
 * Waits for running CSS transitions and animations to end. Axe samples colours at the moment it runs,
 * so a scan right after a theme switch would catch a colour half-way through its transition.
 */
export async function settled(page: Page): Promise<void> {
  await page.evaluate(() =>
    Promise.all(
      document
        .getAnimations()
        // A looping animation (a skeleton pulse) never finishes; only finite ones are waited for.
        .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
        .map((a) => a.finished.catch(() => undefined)),
    ),
  );
}
