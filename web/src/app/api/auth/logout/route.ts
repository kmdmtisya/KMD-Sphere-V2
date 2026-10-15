import { NextResponse } from "next/server";

import { csrfOk } from "@/lib/server/auth/csrf";
import { authRuntime, cookieFrom, CSRF_COOKIE, expiredCookie, SESSION_COOKIE } from "@/lib/server/auth/runtime";
import { destroySession } from "@/lib/server/auth/session";

/**
 * Signs out (POST only, CSRF-checked): deletes the server-side session, revokes the refresh token
 * and ends the Keycloak session through RP-initiated logout, then returns to the portal.
 */
export async function POST(request: Request) {
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return Response.json({ detail: "Sign-in is not configured" }, { status: 503 });
  }
  const { settings } = runtime;
  const isForm = request.headers.get("content-type")?.includes("application/x-www-form-urlencoded") ?? false;
  const submitted = request.headers.get("x-csrf-token") ?? (isForm ? ((await request.formData()).get("csrf") as string | null) : null);
  if (!csrfOk(request, settings.publicUrl, cookieFrom(request, CSRF_COOKIE), submitted)) {
    return Response.json({ detail: "Forbidden" }, { status: 403 });
  }

  const record = await destroySession(runtime.sessions, cookieFrom(request, SESSION_COOKIE));
  if (record?.refreshToken) await runtime.oidc.revokeRefreshToken(settings, record.refreshToken);
  const target = record ? await runtime.oidc.endSessionUrl(settings, record.idToken) : new URL("/", settings.publicUrl);
  const response = NextResponse.redirect(target, 303);
  response.cookies.set(expiredCookie(SESSION_COOKIE));
  response.cookies.set(expiredCookie(CSRF_COOKIE));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
