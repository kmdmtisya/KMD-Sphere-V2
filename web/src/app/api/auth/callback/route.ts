import { NextResponse } from "next/server";

import type { SignInTransaction } from "@/lib/server/auth/oidc";
import {
  authRuntime,
  cookieFrom,
  csrfCookie,
  expiredCookie,
  SESSION_COOKIE,
  sessionCookie,
  SIGN_IN_COOKIE,
} from "@/lib/server/auth/runtime";
import { randomToken, unseal } from "@/lib/server/auth/seal";
import { createSession, destroySession } from "@/lib/server/auth/session";

/** Sign-in transactions older than this are refused. */
const TRANSACTION_MS = 10 * 60 * 1000;

/**
 * Completes sign-in: checks state, nonce and PKCE, exchanges the code server to server, stores the
 * tokens in a new server-side session (a new id at every sign-in, so a planted id is useless) and
 * sets the HttpOnly session cookie and the CSRF cookie. No token reaches the browser.
 */
export async function GET(request: Request) {
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return Response.json({ detail: "Sign-in is not configured" }, { status: 503 });
  }
  const { settings } = runtime;
  const fail = (reason: string) => {
    const response = NextResponse.redirect(new URL(`/?signin=${reason}`, settings.publicUrl), 303);
    response.cookies.set(expiredCookie(SIGN_IN_COOKIE));
    return response;
  };

  const transaction = unseal<SignInTransaction>(cookieFrom(request, SIGN_IN_COOKIE), settings.sessionKey);
  if (!transaction || Date.now() - transaction.startedAt > TRANSACTION_MS) return fail("expired");
  const incoming = new URL(request.url);
  if (incoming.searchParams.has("error")) return fail("cancelled");

  // The redirect URI registered with Keycloak is on the public origin, whatever host served this.
  const current = new URL(`${incoming.pathname}${incoming.search}`, settings.publicUrl);
  let result;
  try {
    result = await runtime.oidc.finishSignIn(settings, current, transaction);
  } catch {
    return fail("failed");
  }

  await destroySession(runtime.sessions, cookieFrom(request, SESSION_COOKIE));
  const id = await createSession(runtime.sessions, result.user, result.tokens);
  const response = NextResponse.redirect(new URL(transaction.returnTo, settings.publicUrl), 303);
  response.cookies.set(sessionCookie(id, settings.absoluteSeconds));
  response.cookies.set(csrfCookie(randomToken(24), settings.absoluteSeconds));
  response.cookies.set(expiredCookie(SIGN_IN_COOKIE));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
