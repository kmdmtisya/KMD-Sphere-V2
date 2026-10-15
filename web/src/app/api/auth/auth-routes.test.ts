import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { SignInTransaction } from "@/lib/server/auth/oidc";
import { setAuthRuntimeForTests, type AuthRuntime } from "@/lib/server/auth/runtime";
import { seal } from "@/lib/server/auth/seal";
import { createSession } from "@/lib/server/auth/session";
import { MemorySessionStore } from "@/lib/server/auth/store";

import { GET as proxyGet, POST as proxyPost } from "../proxy/[...path]/route";
import { GET as callback } from "./callback/route";
import { GET as login } from "./login/route";
import { POST as logout } from "./logout/route";
import { GET as session } from "./session/route";

const KEY = Buffer.alloc(32, 3);
const PUBLIC = "http://localhost:3000";
let runtime: AuthRuntime;
let store: MemorySessionStore;

beforeEach(() => {
  store = new MemorySessionStore();
  runtime = {
    settings: {
      issuer: new URL("http://127.0.0.1:8081/realms/wealthsphere"),
      clientId: "wealthsphere-web",
      clientSecret: "test-secret",
      sessionKey: KEY,
      redisUrl: "redis://unused",
      publicUrl: new URL(PUBLIC),
      idleSeconds: 1800,
      absoluteSeconds: 36000,
    },
    sessions: { store, key: KEY, idleSeconds: 1800, absoluteSeconds: 36000 },
    oidc: {
      startSignIn: vi.fn(async (_s, returnTo: string) => ({
        url: new URL("http://127.0.0.1:8081/realms/wealthsphere/protocol/openid-connect/auth?client_id=wealthsphere-web"),
        transaction: { state: "st", nonce: "no", verifier: "ve", returnTo, startedAt: Date.now() },
      })),
      finishSignIn: vi.fn(async () => ({
        user: { sub: "u-1", name: "Alice", email: "alice@example.test" },
        tokens: { accessToken: "access-1", expiresIn: 300, refreshToken: "refresh-1", idToken: "id-1" },
      })),
      refreshTokens: vi.fn(async () => ({ accessToken: "access-2", expiresIn: 300 })),
      revokeRefreshToken: vi.fn(async () => undefined),
      endSessionUrl: vi.fn(async () => new URL("http://127.0.0.1:8081/realms/wealthsphere/protocol/openid-connect/logout")),
    },
  };
  setAuthRuntimeForTests(runtime);
});

afterEach(() => {
  setAuthRuntimeForTests(null);
  vi.restoreAllMocks();
});

const setCookies = (r: Response) => r.headers.getSetCookie();
const cookie = (r: Response, name: string) => setCookies(r).find((c) => c.startsWith(`${name}=`)) ?? "";
const ctx = (path: string[]) => ({ params: Promise.resolve({ path }) });

async function signedIn(): Promise<{ id: string; headers: Record<string, string> }> {
  const id = await createSession(runtime.sessions, { sub: "u-1", name: "Alice" }, { accessToken: "access-1", expiresIn: 300, refreshToken: "refresh-1", idToken: "id-1" });
  return { id, headers: { cookie: `__Host-ws_session=${id}; __Host-ws_csrf=csrf-1` } };
}

describe("sign-in", () => {
  it("redirects to Keycloak and keeps the PKCE transaction in a sealed HttpOnly cookie", async () => {
    const r = await login(new Request(`${PUBLIC}/api/auth/login?returnTo=//evil.example`));
    expect(r.status).toBe(302);
    expect(r.headers.get("location")).toContain("/protocol/openid-connect/auth");
    const c = cookie(r, "__Host-ws_signin");
    expect(c).toMatch(/HttpOnly/i);
    expect(c).toMatch(/Secure/i);
    expect(c).not.toContain("ve"); // the verifier is sealed, not readable
    expect(vi.mocked(runtime.oidc.startSignIn).mock.calls[0][1]).toBe("/"); // open redirect refused
  });

  it("completes sign-in: a server-side session, HttpOnly session cookie, CSRF cookie, no token to the browser", async () => {
    const tx: SignInTransaction = { state: "st", nonce: "no", verifier: "ve", returnTo: "/portfolio", startedAt: Date.now() };
    const r = await callback(
      new Request(`${PUBLIC}/api/auth/callback?code=abc&state=st`, { headers: { cookie: `__Host-ws_signin=${seal(tx, KEY)}` } }),
    );
    expect(r.status).toBe(303);
    expect(r.headers.get("location")).toBe(`${PUBLIC}/portfolio`);
    const sessionSet = cookie(r, "__Host-ws_session");
    expect(sessionSet).toMatch(/HttpOnly/i);
    expect(sessionSet).toMatch(/SameSite=lax/i);
    expect(cookie(r, "__Host-ws_csrf")).not.toMatch(/HttpOnly/i);
    expect(setCookies(r).join(";")).not.toMatch(/access-1|refresh-1|id-1/);
    expect(store.entries.size).toBe(1);
    const current = vi.mocked(runtime.oidc.finishSignIn).mock.calls[0][1] as URL;
    expect(current.href).toBe(`${PUBLIC}/api/auth/callback?code=abc&state=st`);
  });

  it("refuses a callback without its transaction, or a cancelled one", async () => {
    const expired = await callback(new Request(`${PUBLIC}/api/auth/callback?code=abc&state=st`));
    expect(expired.headers.get("location")).toBe(`${PUBLIC}/?signin=expired`);
    const tx = seal({ state: "st", nonce: "no", verifier: "ve", returnTo: "/", startedAt: Date.now() }, KEY);
    const cancelled = await callback(
      new Request(`${PUBLIC}/api/auth/callback?error=access_denied`, { headers: { cookie: `__Host-ws_signin=${tx}` } }),
    );
    expect(cancelled.headers.get("location")).toBe(`${PUBLIC}/?signin=cancelled`);
    expect(store.entries.size).toBe(0);
  });

  it("replaces an existing session at sign-in (no fixation)", async () => {
    const { id } = await signedIn();
    const tx = seal({ state: "st", nonce: "no", verifier: "ve", returnTo: "/", startedAt: Date.now() }, KEY);
    const r = await callback(
      new Request(`${PUBLIC}/api/auth/callback?code=abc&state=st`, { headers: { cookie: `__Host-ws_signin=${tx}; __Host-ws_session=${id}` } }),
    );
    expect(cookie(r, "__Host-ws_session")).not.toContain(id);
    expect(store.entries.size).toBe(1);
  });
});

describe("session status", () => {
  it("reports the user and expiry, never a token", async () => {
    const { headers } = await signedIn();
    const body = await (await session(new Request(`${PUBLIC}/api/auth/session`, { headers }))).json();
    expect(body.signedIn).toBe(true);
    expect(body.user).toEqual({ name: "Alice", email: null });
    expect(JSON.stringify(body)).not.toMatch(/access-1|refresh-1|id-1/);
    expect((await (await session(new Request(`${PUBLIC}/api/auth/session`))).json()).signedIn).toBe(false);
  });
});

describe("proxy", () => {
  it("answers 401 without a session and forwards nothing", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    expect((await proxyGet(new Request(`${PUBLIC}/api/proxy/me`), ctx(["me"]))).status).toBe(401);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards with the server-held token, without browser cookies, and returns no token", async () => {
    const { headers } = await signedIn();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ id: "u-1" }, { headers: { "set-cookie": "x=y" } }));
    const r = await proxyGet(new Request(`${PUBLIC}/api/proxy/me?x=1`, { headers }), ctx(["me"]));
    expect(r.status).toBe(200);
    const [url, init] = fetchSpy.mock.calls[0] as [URL, RequestInit];
    expect(String(url)).toBe("http://127.0.0.1:8000/api/v1/me?x=1");
    const sent = new Headers(init.headers);
    expect(sent.get("authorization")).toBe("Bearer access-1");
    expect(sent.get("cookie")).toBeNull();
    expect(r.headers.get("set-cookie")).toBeNull();
    expect(r.headers.get("cache-control")).toBe("no-store");
  });

  it("refuses state-changing calls without the CSRF token or from another origin", async () => {
    const { headers } = await signedIn();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const missing = await proxyPost(new Request(`${PUBLIC}/api/proxy/portfolios`, { method: "POST", headers: { ...headers, origin: PUBLIC } }), ctx(["portfolios"]));
    expect(missing.status).toBe(403);
    const foreign = await proxyPost(
      new Request(`${PUBLIC}/api/proxy/portfolios`, { method: "POST", headers: { ...headers, origin: "https://evil.example", "x-csrf-token": "csrf-1" } }),
      ctx(["portfolios"]),
    );
    expect(foreign.status).toBe(403);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards a state-changing call with the token and its body", async () => {
    const { headers } = await signedIn();
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(Response.json({ id: "p-1" }, { status: 201 }));
    const r = await proxyPost(
      new Request(`${PUBLIC}/api/proxy/portfolios`, {
        method: "POST",
        headers: { ...headers, origin: PUBLIC, "x-csrf-token": "csrf-1", "content-type": "application/json" },
        body: JSON.stringify({ name: "Main" }),
      }),
      ctx(["portfolios"]),
    );
    expect(r.status).toBe(201);
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"name":"Main"}');
  });

  it("answers 502 when the API cannot be reached", async () => {
    const { headers } = await signedIn();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("fetch failed"));
    expect((await proxyGet(new Request(`${PUBLIC}/api/proxy/me`, { headers }), ctx(["me"]))).status).toBe(502);
  });
});

describe("sign-out", () => {
  it("needs the CSRF token, then deletes the session, revokes the refresh token and ends the SSO session", async () => {
    const { headers } = await signedIn();
    const forbidden = await logout(new Request(`${PUBLIC}/api/auth/logout`, { method: "POST", headers: { ...headers, origin: PUBLIC } }));
    expect(forbidden.status).toBe(403);
    expect(store.entries.size).toBe(1);

    const form = new URLSearchParams({ csrf: "csrf-1" });
    const r = await logout(
      new Request(`${PUBLIC}/api/auth/logout`, {
        method: "POST",
        headers: { ...headers, origin: PUBLIC, "content-type": "application/x-www-form-urlencoded" },
        body: form,
      }),
    );
    expect(r.status).toBe(303);
    expect(r.headers.get("location")).toContain("/protocol/openid-connect/logout");
    expect(store.entries.size).toBe(0);
    expect(vi.mocked(runtime.oidc.revokeRefreshToken).mock.calls[0][1]).toBe("refresh-1");
    expect(cookie(r, "__Host-ws_session")).toMatch(/Max-Age=0/i);
  });
});
