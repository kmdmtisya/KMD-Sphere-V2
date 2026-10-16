import { NextResponse } from "next/server";

/**
 * The Content-Security-Policy (P14-T19, QG-29.5), set per request so the origins it names (the
 * identity provider for the sign-out redirect, the live-quotes socket) come from the runtime
 * configuration, not the build.
 *
 * Inline scripts are allowed ('unsafe-inline') and that is a recorded residual risk
 * (docs/web/WEB_THREAT_MODEL.md): Next.js emits inline scripts for streaming and page data whose
 * content differs per page and request, so they cannot be allow-listed by hash; and a nonce would
 * make every page dynamic, which Partial Prerendering (ADR-0018) cannot do for a static shell. What
 * the policy does enforce: nothing loads from another origin, no plugins, no framing, no base-tag
 * hijack, forms post only to this site and the identity provider, and scripts may connect only to
 * this site and the configured live-quotes socket. The compensating controls are output encoding
 * (React), no HTML rendering of user or AI text, and a lint rule against dangerouslySetInnerHTML.
 */
function origin(value: string | undefined): string | null {
  if (!value) return null;
  try {
    return new URL(value).origin;
  } catch {
    return null;
  }
}

export function policy(env: Record<string, string | undefined> = process.env): string {
  const dev = env.NODE_ENV === "development";
  const idp = origin(env.WS_OIDC_ISSUER);
  const stream = origin(env.WS_FOREX_STREAM_URL?.replace(/^ws/, "http")) ?? origin(env.WS_API_BASE_URL);
  const socket = stream ? stream.replace(/^http/, "ws") : null;
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${dev ? " 'unsafe-eval'" : ""}`,
    // React style attributes (widths, chart sizing) need inline styles.
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self'",
    `connect-src 'self'${socket ? ` ${socket}` : ""}${dev ? " ws: wss:" : ""}`,
    "object-src 'none'",
    "base-uri 'self'",
    `form-action 'self'${idp ? ` ${idp}` : ""}`,
    "frame-ancestors 'none'",
  ];
  if (env.NODE_ENV === "production" && env.WS_PUBLIC_URL?.startsWith("https:")) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

export function proxy() {
  const response = NextResponse.next();
  response.headers.set("Content-Security-Policy", policy());
  return response;
}

export const config = {
  // Pages and routes, not static assets.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
