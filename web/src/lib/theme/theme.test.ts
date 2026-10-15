import { runInNewContext } from "node:vm";

import { describe, expect, it } from "vitest";

import { nextPreference, parsePreference, resolveTheme, THEME_BOOT_SCRIPT, themeCookie } from "./theme";

describe("theme preference", () => {
  it("parses only the three words; anything else is system", () => {
    expect(parsePreference("light")).toBe("light");
    expect(parsePreference("dark")).toBe("dark");
    expect(parsePreference("system")).toBe("system");
    expect(parsePreference("purple")).toBe("system");
    expect(parsePreference(undefined)).toBe("system");
  });

  it("resolves system from the device and never overrides an explicit choice", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("cycles Light, Dark, System", () => {
    expect([nextPreference("light"), nextPreference("dark"), nextPreference("system")]).toEqual(["dark", "system", "light"]);
  });

  it("writes a host-only, secure cookie that holds only the word", () => {
    expect(themeCookie("dark")).toBe("__Host-ws_theme=dark; Path=/; Max-Age=31536000; SameSite=Lax; Secure");
  });
});

describe("boot script", () => {
  function boot(cookie: string): string | null {
    let applied: string | null = null;
    const document = {
      cookie,
      documentElement: { setAttribute: (_name: string, value: string) => (applied = value) },
    };
    runInNewContext(THEME_BOOT_SCRIPT, { document });
    return applied;
  }

  it("applies the saved choice before the first paint", () => {
    expect(boot("a=1; __Host-ws_theme=dark; b=2")).toBe("dark");
    expect(boot("__Host-ws_theme=light")).toBe("light");
  });

  it("falls back to system without a cookie, or with a forged value", () => {
    expect(boot("")).toBe("system");
    expect(boot('__Host-ws_theme=dark"onload=alert(1)')).toBe("system");
    expect(boot("x__Host-ws_theme=dark")).toBe("system");
  });
});
