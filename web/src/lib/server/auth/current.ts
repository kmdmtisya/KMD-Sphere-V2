import "server-only";

import { cookies } from "next/headers";

import { serverConfig } from "../config";
import { authRuntime, SESSION_COOKIE } from "./runtime";
import { accessTokenFor, readSession, type SessionUser } from "./session";

/**
 * The signed-in user for a server-rendered page (P14-T06): the session, a usable access token
 * (refreshed when due) and the realm roles read from it. Roles only decide what the navigation
 * shows; the API enforces every permission itself.
 */
export type CurrentSession = { user: SessionUser; accessToken: string; roles: string[] };

export function rolesFromToken(accessToken: string): string[] {
  try {
    const payload = JSON.parse(Buffer.from(accessToken.split(".")[1] ?? "", "base64url").toString("utf8"));
    const roles = payload?.realm_access?.roles;
    return Array.isArray(roles) ? roles.filter((r): r is string => typeof r === "string") : [];
  } catch {
    return [];
  }
}

export async function currentSession(): Promise<CurrentSession | null> {
  const id = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!id) return null;
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return null;
  }
  const record = await readSession(runtime.sessions, id);
  if (!record) return null;
  const token = await accessTokenFor(runtime.sessions, id, record, (rt) => runtime.oidc.refreshTokens(runtime.settings, rt));
  if (!token) return null;
  return { user: record.user, accessToken: token, roles: rolesFromToken(token) };
}

/** Calls the API as the signed-in user (server side only). Returns null when it cannot be reached. */
export async function apiStatus(session: CurrentSession, path: string): Promise<number | null> {
  try {
    const response = await fetch(new URL(path, serverConfig().apiBaseUrl), {
      headers: { authorization: `Bearer ${session.accessToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    await response.body?.cancel();
    return response.status;
  } catch {
    return null;
  }
}

/** Whether the server has the forex module on (DEC-23): the endpoints answer 404 when it is off. */
export async function forexEnabled(session: CurrentSession): Promise<boolean> {
  return (await apiStatus(session, "/api/v1/forex/instruments")) === 200;
}

/** The account's display name and email from the API (`/me`), the source of truth for the profile. */
export async function accountOf(session: CurrentSession): Promise<{ name: string; email?: string }> {
  try {
    const response = await fetch(new URL("/api/v1/me", serverConfig().apiBaseUrl), {
      headers: { authorization: `Bearer ${session.accessToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (response.ok) {
      const me = (await response.json()) as { display_name?: string | null; email?: string | null };
      const email = me.email ?? undefined;
      return { name: me.display_name || email || "Your account", email };
    }
  } catch {
    // Fall back to what the sign-in gave us.
  }
  const email = session.user.email;
  return { name: session.user.name ?? email ?? "Your account", email };
}
