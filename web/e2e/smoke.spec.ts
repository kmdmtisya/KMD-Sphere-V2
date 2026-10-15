import { expect, test } from "@playwright/test";

test("the foundation page renders with a heading and the baseline security headers", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "WealthSphere" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await expect(page.locator("html")).toHaveAttribute("data-theme-pref", "system");
  const headers = response?.headers() ?? {};
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("System appearance follows the browser's colour scheme without a reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await page.goto("/");
  const background = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const light = await background();
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(background).not.toBe(light);
});

test("the BFF health route reports the web, and the API when it is running", async ({ request }) => {
  const response = await request.get("/api/health");
  expect(response.status()).toBe(200);
  const body = await response.json();
  expect(body.web).toBe("ok");
  if (process.env.WS_E2E_EXPECT_API === "1") expect(body.api).toBe("ok");
  else expect(["ok", "unavailable"]).toContain(body.api);
});

test("the BFF proxy refuses everything until sign-in exists, and paths outside the allow-list", async ({ request }) => {
  expect((await request.get("/api/proxy/portfolios")).status()).toBe(401);
  expect((await request.get("/api/proxy/a%20b")).status()).toBe(404);
});
