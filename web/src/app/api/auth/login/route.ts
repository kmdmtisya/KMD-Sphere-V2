import { NextResponse } from "next/server";

import { authRuntime, safeReturnTo, signInCookie } from "@/lib/server/auth/runtime";
import { seal } from "@/lib/server/auth/seal";

/**
 * Starts sign-in (P14-T05): Authorization Code with PKCE, state and nonce. The transaction is sealed
 * in a short-lived HttpOnly cookie; the browser is sent to Keycloak, which applies the realm's
 * password, MFA and lockout policies.
 */
export async function GET(request: Request) {
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return Response.json({ detail: "Sign-in is not configured" }, { status: 503 });
  }
  const { settings, oidc } = runtime;
  const returnTo = safeReturnTo(new URL(request.url).searchParams.get("returnTo"));
  const { url, transaction } = await oidc.startSignIn(settings, returnTo);
  const response = NextResponse.redirect(url, 302);
  response.cookies.set(signInCookie(seal(transaction, settings.sessionKey)));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
