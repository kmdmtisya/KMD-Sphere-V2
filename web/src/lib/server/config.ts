import "server-only";

/** Hosts where plain HTTP is acceptable: the local stack only (as on mobile debug builds). */
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export type ServerConfig = {
  /** The FastAPI base URL the BFF calls server to server. The browser never sees it. */
  apiBaseUrl: URL;
  /** Where the browser opens the live-quotes WebSocket (`WS_FOREX_STREAM_URL`; wss in production). */
  forexStreamUrl: string;
};

/**
 * Reads the BFF configuration from the environment. `WS_API_BASE_URL` must be https, or http to a
 * loopback address for local development. P14-T21 adds the full start-up validation.
 */
export function serverConfig(
  env: Record<string, string | undefined> = process.env,
): ServerConfig {
  const raw = env.WS_API_BASE_URL ?? "http://127.0.0.1:8000";
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    throw new Error("WS_API_BASE_URL is not a valid URL");
  }
  const local = url.protocol === "http:" && LOOPBACK.has(url.hostname);
  if (url.protocol !== "https:" && !local) {
    throw new Error(
      "WS_API_BASE_URL must use https (plain http is allowed only to a loopback address)",
    );
  }
  if (url.username || url.password) {
    throw new Error("WS_API_BASE_URL must not contain credentials");
  }
  return {
    apiBaseUrl: url,
    forexStreamUrl: streamUrl(env.WS_FOREX_STREAM_URL, url),
  };
}

/**
 * The live-quotes socket address handed to the browser. Defaults to the API's own address with the
 * websocket scheme. It must be wss, or ws to a loopback address for local development, and carry no
 * credentials or query (a ticket or token is never put in a URL).
 */
export function streamUrl(raw: string | undefined, api: URL): string {
  const fallback = new URL("/api/v1/forex/stream", api);
  fallback.protocol = api.protocol === "https:" ? "wss:" : "ws:";
  let url: URL;
  try {
    url = raw ? new URL(raw) : fallback;
  } catch {
    throw new Error("WS_FOREX_STREAM_URL is not a valid URL");
  }
  const local = url.protocol === "ws:" && LOOPBACK.has(url.hostname);
  if (url.protocol !== "wss:" && !local) {
    throw new Error(
      "WS_FOREX_STREAM_URL must use wss (plain ws is allowed only to a loopback address)",
    );
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(
      "WS_FOREX_STREAM_URL must not contain credentials, a query or a fragment",
    );
  }
  return url.toString();
}
