import "server-only";

import { safeEqual } from "./seal";

/**
 * CSRF defence for state-changing requests (docs/web/WEB_PORTAL_ARCHITECTURE.md §3): the request
 * must come from the portal's own origin (Origin, or Referer when Origin is absent) and carry the
 * double-submit token from the readable `__Host-ws_csrf` cookie, in the `X-CSRF-Token` header (fetch)
 * or the `csrf` form field (plain HTML forms). SameSite=Lax on the cookies is a second layer.
 */
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export function isSafeMethod(method: string): boolean {
  return SAFE_METHODS.has(method.toUpperCase());
}

export function sameOrigin(request: Request, publicUrl: URL): boolean {
  const origin = request.headers.get("origin");
  if (origin) return origin === publicUrl.origin;
  const referer = request.headers.get("referer");
  if (!referer) return false;
  try {
    return new URL(referer).origin === publicUrl.origin;
  } catch {
    return false;
  }
}

/** True when the state-changing request passes both checks; safe methods always pass. */
export function csrfOk(request: Request, publicUrl: URL, cookieToken: string | undefined, submitted: string | null): boolean {
  if (isSafeMethod(request.method)) return true;
  if (!sameOrigin(request, publicUrl)) return false;
  if (!cookieToken || !submitted) return false;
  return safeEqual(cookieToken, submitted);
}
