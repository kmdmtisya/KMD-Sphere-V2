/**
 * The BFF proxy's allow-list (docs/web/WEB_PORTAL_ARCHITECTURE.md "Forwarding"): the browser may
 * reach only `/api/v1/*` on the API, with the standard methods, through plain path segments. The API
 * stays the authority on what a signed-in user may see; this only stops the proxy from becoming an
 * open relay (no other paths, hosts, schemes or traversal).
 */
export const ALLOWED_METHODS: ReadonlySet<string> = new Set(["GET", "POST", "PUT", "PATCH", "DELETE"]);

/** One path segment: letters, digits and `-._~` (ids, UUIDs, pair symbols such as EUR_USD). */
const SEGMENT = /^[A-Za-z0-9._~-]+$/;
const MAX_SEGMENTS = 12;

/** Returns the API path to forward to, or null when the request is not allowed. */
export function apiPathFor(method: string, segments: readonly string[] | undefined): string | null {
  if (!ALLOWED_METHODS.has(method)) return null;
  if (!segments || segments.length === 0 || segments.length > MAX_SEGMENTS) return null;
  for (const segment of segments) {
    if (!SEGMENT.test(segment) || segment === "." || segment === "..") return null;
  }
  return `/api/v1/${segments.join("/")}`;
}
