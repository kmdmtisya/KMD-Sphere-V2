"use client";

/**
 * Calls to the API through the BFF proxy, from the browser (P14-T06, extended in P14-T08). The session
 * cookie goes automatically; state-changing calls add the CSRF token from its readable cookie. Money
 * values stay decimal strings (ADR-0003).
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    /** The server's problem detail (never a stack trace), for showing to the person. */
    readonly detail?: string,
  ) {
    super(`API answered ${status}`);
  }
}

export function csrf(): string | undefined {
  const raw = /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1];
  return raw ? decodeURIComponent(raw) : undefined;
}

async function failure(response: Response): Promise<ApiError> {
  let detail: string | undefined;
  try {
    const body = (await response.json()) as { detail?: unknown; title?: unknown; errors?: { field?: string; message?: string }[] };
    const fields = Array.isArray(body.errors) ? body.errors.map((e) => (e.field ? `${e.field}: ${e.message}` : e.message)).filter(Boolean).join("; ") : "";
    if (typeof body.detail === "string") detail = body.detail;
    else if (typeof body.title === "string") detail = body.title;
    if (fields) detail = detail ? `${detail} (${fields})` : fields;
  } catch {
    // No JSON body.
  }
  return new ApiError(response.status, detail);
}

export type WriteOptions = { idempotencyKey?: string };

async function send<T>(method: string, path: string, body: unknown, options: WriteOptions = {}): Promise<T> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (body !== undefined) headers["content-type"] = "application/json";
  if (method !== "GET") {
    const token = csrf();
    if (token) headers["x-csrf-token"] = token;
  }
  if (options.idempotencyKey) headers["idempotency-key"] = options.idempotencyKey;
  const response = await fetch(`/api/proxy/${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  if (!response.ok) throw await failure(response);
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const apiGet = <T>(path: string) => send<T>("GET", path, undefined);
export const apiPost = <T>(path: string, body: unknown, options?: WriteOptions) => send<T>("POST", path, body, options);
export const apiPatch = <T>(path: string, body: unknown) => send<T>("PATCH", path, body);
export const apiPut = <T>(path: string, body: unknown) => send<T>("PUT", path, body);
export const apiDelete = (path: string) => send<void>("DELETE", path, undefined);
