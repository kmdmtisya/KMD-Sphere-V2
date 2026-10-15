import { serverConfig } from "@/lib/server/config";

/**
 * Web health: the web server answers, and reports whether it can reach the API's liveness probe
 * server to server. It returns no data and no configuration.
 */
export async function GET() {
  let api: "ok" | "unavailable" = "unavailable";
  try {
    const response = await fetch(new URL("/health/live", serverConfig().apiBaseUrl), {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    if (response.ok) api = "ok";
  } catch {
    // Unreachable or misconfigured API: reported as unavailable.
  }
  return Response.json({ web: "ok", api }, { headers: { "Cache-Control": "no-store" } });
}
