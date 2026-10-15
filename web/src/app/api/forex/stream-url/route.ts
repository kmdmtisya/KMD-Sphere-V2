import {
  authRuntime,
  cookieFrom,
  SESSION_COOKIE,
} from "@/lib/server/auth/runtime";
import { readSession } from "@/lib/server/auth/session";
import { serverConfig } from "@/lib/server/config";

/**
 * Where the browser opens the live-quotes WebSocket (P14-T13.2). Signed-in sessions only. The
 * browser then asks the proxy for a single-use ticket (`POST /api/proxy/forex/stream-ticket`) and
 * sends it as the socket's first message: no token or ticket is ever put in a URL.
 */
export async function GET(request: Request) {
  const headers = { "Cache-Control": "no-store" };
  const sessionId = cookieFrom(request, SESSION_COOKIE);
  if (!sessionId)
    return Response.json({ detail: "Not signed in" }, { status: 401, headers });
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return Response.json(
      { detail: "Sign-in is not configured" },
      { status: 503, headers },
    );
  }
  if (!(await readSession(runtime.sessions, sessionId))) {
    return Response.json({ detail: "Not signed in" }, { status: 401, headers });
  }
  return Response.json({ url: serverConfig().forexStreamUrl }, { headers });
}
