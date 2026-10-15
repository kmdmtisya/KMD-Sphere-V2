import { apiPathFor } from "@/lib/bff/allowlist";
import { csrfOk } from "@/lib/server/auth/csrf";
import { authRuntime, cookieFrom, CSRF_COOKIE, SESSION_COOKIE } from "@/lib/server/auth/runtime";
import { accessTokenFor, readSession } from "@/lib/server/auth/session";
import { serverConfig } from "@/lib/server/config";

/**
 * The BFF proxy (P14-T05, WEB_PORTAL_ARCHITECTURE.md §3 "Forwarding"): only allow-listed
 * `/api/v1/*` paths; a live session; the CSRF checks on every state-changing request; then the call is
 * forwarded with the session's access token (refreshed shortly before it expires). The API remains
 * the authority on what the user may see. Cookies never go upstream and tokens never come back.
 */
const REQUEST_HEADERS = ["accept", "accept-language", "content-type", "if-match", "if-none-match", "x-correlation-id"];
const RESPONSE_HEADERS = ["content-type", "content-disposition", "etag", "retry-after", "x-correlation-id", "location"];
const MAX_BODY_BYTES = 1_000_000;

const json = (status: number, detail: string) =>
  Response.json({ detail }, { status, headers: { "Cache-Control": "no-store" } });

async function handle(request: Request, ctx: { params: Promise<{ path?: string[] }> }) {
  const { path } = await ctx.params;
  const target = apiPathFor(request.method, path);
  if (target === null) return json(404, "Not found");

  const sessionId = cookieFrom(request, SESSION_COOKIE);
  if (!sessionId) return json(401, "Not signed in");
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return json(503, "Sign-in is not configured");
  }
  if (!csrfOk(request, runtime.settings.publicUrl, cookieFrom(request, CSRF_COOKIE), request.headers.get("x-csrf-token"))) {
    return json(403, "Forbidden");
  }
  const record = await readSession(runtime.sessions, sessionId);
  if (!record) return json(401, "Not signed in");
  const token = await accessTokenFor(runtime.sessions, sessionId, record, (refreshToken) =>
    runtime.oidc.refreshTokens(runtime.settings, refreshToken),
  );
  if (!token) return json(401, "Not signed in");

  const length = Number.parseInt(request.headers.get("content-length") ?? "0", 10);
  if (length > MAX_BODY_BYTES) return json(413, "Request too large");

  const url = new URL(target + new URL(request.url).search, serverConfig().apiBaseUrl);
  const headers = new Headers({ authorization: `Bearer ${token}` });
  for (const name of REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const hasBody = !["GET", "HEAD"].includes(request.method);
  let upstream: Response;
  try {
    upstream = await fetch(url, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return json(502, "The service is unavailable");
  }
  const out = new Headers({ "Cache-Control": "no-store" });
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Streamed responses (the AI chat's server-sent events) pass through as they arrive.
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };
