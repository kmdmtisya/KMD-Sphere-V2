import { describe, expect, it } from "vitest";

import { csrfOk } from "./csrf";
import { csrfCookie, expiredCookie, safeReturnTo, sessionCookie, signInCookie } from "./runtime";
import { randomToken, safeEqual, seal, storeKey, unseal } from "./seal";
import { accessTokenFor, createSession, destroySession, readSession, type SessionDeps } from "./session";
import { authSettings } from "./settings";
import { MemorySessionStore } from "./store";

const KEY = Buffer.alloc(32, 7);
const OTHER_KEY = Buffer.alloc(32, 9);

describe("seal", () => {
  it("round-trips, and refuses tampered values and other keys", () => {
    const sealed = seal({ a: 1, token: "secret" }, KEY);
    expect(sealed).not.toContain("secret");
    expect(unseal(sealed, KEY)).toEqual({ a: 1, token: "secret" });
    expect(unseal(sealed, OTHER_KEY)).toBeNull();
    const tampered = sealed.slice(0, -2) + (sealed.endsWith("A") ? "BB" : "AA");
    expect(unseal(tampered, KEY)).toBeNull();
    expect(unseal("", KEY)).toBeNull();
    expect(unseal("not-base64!", KEY)).toBeNull();
  });

  it("makes unique tokens and store keys that do not reveal the session id", () => {
    const a = randomToken();
    expect(a).not.toBe(randomToken());
    expect(a.length).toBeGreaterThanOrEqual(43);
    expect(storeKey(a)).not.toContain(a);
    expect(storeKey(a)).toBe(storeKey(a));
    expect(safeEqual("abc", "abc")).toBe(true);
    expect(safeEqual("abc", "abd")).toBe(false);
    expect(safeEqual("abc", "abcd")).toBe(false);
  });
});

function harness(idleSeconds = 1800, absoluteSeconds = 36000) {
  let now = 1_000_000;
  const store = new MemorySessionStore(() => now);
  const deps: SessionDeps = { store, key: KEY, idleSeconds, absoluteSeconds, now: () => now };
  return { store, deps, advance: (ms: number) => (now += ms) };
}

const TOKENS = { accessToken: "access-1", expiresIn: 300, refreshToken: "refresh-1", idToken: "id-1" };
const USER = { sub: "u-1", name: "Alice", email: "alice@example.test" };

describe("sessions", () => {
  it("stores tokens sealed, under a hashed key", async () => {
    const { store, deps } = harness();
    const id = await createSession(deps, USER, TOKENS);
    const [[key, entry]] = [...store.entries.entries()];
    expect(key).toBe(storeKey(id));
    expect(entry.value).not.toContain("access-1");
    expect(entry.value).not.toContain("refresh-1");
    expect((await readSession(deps, id))?.user).toEqual(USER);
  });

  it("ends after the idle timeout, and activity restarts the idle timer", async () => {
    const { deps, advance } = harness(60, 3600);
    const id = await createSession(deps, USER, TOKENS);
    advance(50_000);
    expect(await readSession(deps, id)).not.toBeNull(); // touched
    advance(50_000);
    expect(await readSession(deps, id)).not.toBeNull();
    advance(61_000);
    expect(await readSession(deps, id)).toBeNull();
  });

  it("a status read does not keep an idle session alive", async () => {
    const { deps, advance } = harness(60, 3600);
    const id = await createSession(deps, USER, TOKENS);
    advance(50_000);
    expect(await readSession(deps, id, { touch: false })).not.toBeNull();
    advance(11_000);
    expect(await readSession(deps, id, { touch: false })).toBeNull();
  });

  it("ends at the absolute timeout even when active", async () => {
    const { deps, advance } = harness(60, 300);
    const id = await createSession(deps, USER, TOKENS);
    for (let i = 0; i < 5; i++) {
      advance(55_000);
      expect(await readSession(deps, id)).not.toBeNull();
    }
    advance(30_000);
    expect(await readSession(deps, id)).toBeNull();
  });

  it("is removed on sign-out and returns what it held", async () => {
    const { deps } = harness();
    const id = await createSession(deps, USER, TOKENS);
    expect((await destroySession(deps, id))?.refreshToken).toBe("refresh-1");
    expect(await readSession(deps, id)).toBeNull();
    expect(await destroySession(deps, undefined)).toBeNull();
  });

  it("refreshes the access token shortly before it expires", async () => {
    const { deps, advance } = harness();
    const id = await createSession(deps, USER, TOKENS);
    const refresh = async (rt: string) => ({ accessToken: `access-after-${rt}`, expiresIn: 300, refreshToken: "refresh-2" });
    let record = (await readSession(deps, id))!;
    expect(await accessTokenFor(deps, id, record, refresh)).toBe("access-1");
    advance(280_000);
    record = (await readSession(deps, id))!;
    expect(await accessTokenFor(deps, id, record, refresh)).toBe("access-after-refresh-1");
    record = (await readSession(deps, id))!;
    expect(record.refreshToken).toBe("refresh-2");
    expect(record.idToken).toBe("id-1");
  });

  it("ends the session when the refresh fails or there is no refresh token", async () => {
    const { deps, advance } = harness();
    const id = await createSession(deps, USER, TOKENS);
    advance(290_000);
    const record = (await readSession(deps, id))!;
    expect(await accessTokenFor(deps, id, record, async () => Promise.reject(new Error("invalid_grant")))).toBeNull();
    expect(await readSession(deps, id)).toBeNull();

    const id2 = await createSession(deps, USER, { accessToken: "a", expiresIn: 10 });
    const record2 = (await readSession(deps, id2))!;
    expect(await accessTokenFor(deps, id2, record2, async () => TOKENS)).toBeNull();
  });
});

const PUBLIC = new URL("http://localhost:3000");
const req = (method: string, headers: Record<string, string>) => new Request("http://localhost:3000/api/proxy/x", { method, headers });

describe("csrfOk", () => {
  it("lets safe methods through", () => {
    expect(csrfOk(req("GET", {}), PUBLIC, undefined, null)).toBe(true);
  });

  it("needs the portal origin and the matching double-submit token", () => {
    const ok = { origin: "http://localhost:3000" };
    expect(csrfOk(req("POST", ok), PUBLIC, "t1", "t1")).toBe(true);
    expect(csrfOk(req("POST", ok), PUBLIC, "t1", "t2")).toBe(false);
    expect(csrfOk(req("POST", ok), PUBLIC, undefined, "t1")).toBe(false);
    expect(csrfOk(req("POST", ok), PUBLIC, "t1", null)).toBe(false);
    expect(csrfOk(req("DELETE", { origin: "https://evil.example" }), PUBLIC, "t1", "t1")).toBe(false);
    expect(csrfOk(req("PATCH", { referer: "http://localhost:3000/portfolio" }), PUBLIC, "t1", "t1")).toBe(true);
    expect(csrfOk(req("PATCH", { referer: "https://evil.example/" }), PUBLIC, "t1", "t1")).toBe(false);
    expect(csrfOk(req("PUT", {}), PUBLIC, "t1", "t1")).toBe(false);
  });
});

describe("cookies and redirects", () => {
  it("keeps the session cookie away from scripts and binds every cookie to this origin", () => {
    for (const c of [sessionCookie("s", 60), csrfCookie("c", 60), signInCookie("t"), expiredCookie("__Host-ws_session")]) {
      expect(c.name.startsWith("__Host-")).toBe(true);
      expect(c).toMatchObject({ secure: true, path: "/", sameSite: "lax" });
      expect("domain" in c).toBe(false);
    }
    expect(sessionCookie("s", 60).httpOnly).toBe(true);
    expect(signInCookie("t").httpOnly).toBe(true);
    expect(csrfCookie("c", 60).httpOnly).toBe(false);
  });

  it("only returns to same-site paths after sign-in", () => {
    expect(safeReturnTo("/portfolio?tab=holdings")).toBe("/portfolio?tab=holdings");
    expect(safeReturnTo("https://evil.example")).toBe("/");
    expect(safeReturnTo("//evil.example")).toBe("/");
    expect(safeReturnTo("/\\evil.example")).toBe("/");
    expect(safeReturnTo(null)).toBe("/");
  });
});

describe("authSettings", () => {
  const env = {
    WS_OIDC_ISSUER: "http://127.0.0.1:8081/realms/wealthsphere",
    WS_OIDC_CLIENT_SECRET: "s",
    WS_SESSION_KEY: Buffer.alloc(32, 1).toString("base64url"),
    WS_REDIS_URL: "redis://127.0.0.1:6380/1",
    WS_PUBLIC_URL: "http://localhost:3000",
  };

  it("defaults to the realm's idle and absolute lifetimes", () => {
    const s = authSettings(env);
    expect([s.idleSeconds, s.absoluteSeconds]).toEqual([1800, 36000]);
    expect(s.clientId).toBe("wealthsphere-web");
  });

  it("refuses missing secrets, short keys, plain http to other hosts and inverted timeouts", () => {
    expect(() => authSettings({ ...env, WS_OIDC_CLIENT_SECRET: undefined })).toThrow(/WS_OIDC_CLIENT_SECRET/);
    expect(() => authSettings({ ...env, WS_SESSION_KEY: "c2hvcnQ" })).toThrow(/32 bytes/);
    expect(() => authSettings({ ...env, WS_PUBLIC_URL: "http://portal.example" })).toThrow(/https/);
    expect(() => authSettings({ ...env, WS_SESSION_IDLE_SECONDS: "100", WS_SESSION_ABSOLUTE_SECONDS: "50" })).toThrow(/idle/);
  });
});
