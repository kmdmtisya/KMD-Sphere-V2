"use client";

/**
 * Calls to the API through the BFF proxy, from the browser (P14-T06). The session cookie goes
 * automatically; state-changing calls add the CSRF token from its readable cookie. Money values stay
 * decimal strings (ADR-0003).
 */
export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`API answered ${status}`);
  }
}

function csrf(): string | undefined {
  const raw = /(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1];
  return raw ? decodeURIComponent(raw) : undefined;
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api/proxy/${path}`, { headers: { accept: "application/json" } });
  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  const headers: Record<string, string> = { "content-type": "application/json" };
  const token = csrf();
  if (token) headers["x-csrf-token"] = token;
  const response = await fetch(`/api/proxy/${path}`, { method: "PATCH", headers, body: JSON.stringify(body) });
  if (!response.ok) throw new ApiError(response.status);
  return (await response.json()) as T;
}
