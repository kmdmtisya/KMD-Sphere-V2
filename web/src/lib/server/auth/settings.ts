import "server-only";

/**
 * BFF authentication settings (P14-T05, docs/web/WEB_PORTAL_ARCHITECTURE.md §3). Secrets come from
 * the environment (the secret store in deployed environments; web/.env.local locally, written by
 * `python scripts/keycloak_dev.py web-client`) and are never logged.
 */
const LOOPBACK = new Set(["127.0.0.1", "localhost", "[::1]"]);

export type AuthSettings = {
  issuer: URL;
  clientId: string;
  clientSecret: string;
  /** 32-byte key that seals session records and the sign-in transaction (AES-256-GCM). */
  sessionKey: Buffer;
  redisUrl: string;
  /** The portal's public origin; the callback and logout URLs derive from it. */
  publicUrl: URL;
  /** Idle and absolute session lifetimes, matching the realm (ssoSessionIdleTimeout, ssoSessionMaxLifespan). */
  idleSeconds: number;
  absoluteSeconds: number;
};

function secureOrLoopback(url: URL, name: string): URL {
  if (url.protocol === "https:" || (url.protocol === "http:" && LOOPBACK.has(url.hostname))) return url;
  throw new Error(`${name} must use https (plain http is allowed only to a loopback address)`);
}

function required(env: Record<string, string | undefined>, name: string): string {
  const value = env[name];
  if (!value) throw new Error(`${name} is not set (see web/README.md, "Configuration")`);
  return value;
}

function seconds(env: Record<string, string | undefined>, name: string, fallback: number): number {
  const raw = env[name];
  if (raw === undefined) return fallback;
  const n = Number.parseInt(raw, 10);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`${name} must be a positive number of seconds`);
  return n;
}

export function authSettings(env: Record<string, string | undefined> = process.env): AuthSettings {
  const key = Buffer.from(required(env, "WS_SESSION_KEY"), "base64url");
  if (key.length !== 32) throw new Error("WS_SESSION_KEY must be 32 bytes, base64url-encoded");
  const idleSeconds = seconds(env, "WS_SESSION_IDLE_SECONDS", 1800);
  const absoluteSeconds = seconds(env, "WS_SESSION_ABSOLUTE_SECONDS", 36000);
  if (idleSeconds > absoluteSeconds) throw new Error("the idle timeout must not exceed the absolute timeout");
  return {
    issuer: secureOrLoopback(new URL(required(env, "WS_OIDC_ISSUER")), "WS_OIDC_ISSUER"),
    clientId: env.WS_OIDC_CLIENT_ID ?? "wealthsphere-web",
    clientSecret: required(env, "WS_OIDC_CLIENT_SECRET"),
    sessionKey: key,
    redisUrl: required(env, "WS_REDIS_URL"),
    publicUrl: secureOrLoopback(new URL(required(env, "WS_PUBLIC_URL")), "WS_PUBLIC_URL"),
    idleSeconds,
    absoluteSeconds,
  };
}

export function isLoopback(url: URL): boolean {
  return LOOPBACK.has(url.hostname);
}
