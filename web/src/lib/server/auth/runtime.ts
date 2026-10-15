import "server-only";

import * as oidc from "./oidc";
import type { SessionDeps } from "./session";
import { authSettings, type AuthSettings } from "./settings";
import { RedisSessionStore, type SessionStore } from "./store";

/**
 * The BFF's authentication runtime: settings, the session store and the OIDC calls, created once per
 * process. Unit tests replace it with a memory store and fake OIDC calls (`setAuthRuntimeForTests`).
 */
export type AuthRuntime = {
  settings: AuthSettings;
  sessions: SessionDeps;
  oidc: Pick<typeof oidc, "startSignIn" | "finishSignIn" | "refreshTokens" | "revokeRefreshToken" | "endSessionUrl">;
};

let runtime: AuthRuntime | null = null;

export function authRuntime(): AuthRuntime {
  if (!runtime) {
    const settings = authSettings();
    const store: SessionStore = new RedisSessionStore(settings.redisUrl);
    runtime = {
      settings,
      sessions: { store, key: settings.sessionKey, idleSeconds: settings.idleSeconds, absoluteSeconds: settings.absoluteSeconds },
      oidc,
    };
  }
  return runtime;
}

export function setAuthRuntimeForTests(value: AuthRuntime | null): void {
  runtime = value;
}

/**
 * Cookies (WEB_PORTAL_ARCHITECTURE.md §3). `__Host-` binds them to this exact origin: Secure, path
 * "/", no Domain. Only the CSRF token is readable by scripts; it is not a credential.
 */
export const SESSION_COOKIE = "__Host-ws_session";
export const CSRF_COOKIE = "__Host-ws_csrf";
export const SIGN_IN_COOKIE = "__Host-ws_signin";

const base = { secure: true, path: "/", sameSite: "lax" as const };

export function sessionCookie(value: string, maxAgeSeconds: number) {
  return { name: SESSION_COOKIE, value, ...base, httpOnly: true, maxAge: maxAgeSeconds };
}

export function csrfCookie(value: string, maxAgeSeconds: number) {
  return { name: CSRF_COOKIE, value, ...base, httpOnly: false, maxAge: maxAgeSeconds };
}

export function signInCookie(value: string) {
  return { name: SIGN_IN_COOKIE, value, ...base, httpOnly: true, maxAge: 600 };
}

export function expiredCookie(name: string) {
  return { name, value: "", ...base, httpOnly: name !== CSRF_COOKIE, maxAge: 0 };
}

/** Reads one cookie from a request's Cookie header. */
export function cookieFrom(request: Request, name: string): string | undefined {
  const header = request.headers.get("cookie");
  if (!header) return undefined;
  for (const part of header.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k === name) return decodeURIComponent(v.join("="));
  }
  return undefined;
}

/** Only same-site paths are accepted as a destination after sign-in (no open redirects). */
export function safeReturnTo(value: string | null | undefined): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) return "/";
  return value;
}
