import "server-only";

import { randomToken, seal, storeKey, unseal } from "./seal";
import type { SessionStore } from "./store";

/**
 * Server-side sessions (DEC-31): the tokens live only here, sealed in the store under a hash of the
 * session id; the browser holds only the opaque id in an HttpOnly cookie. Sessions end after the
 * idle or the absolute timeout (the realm's values), on sign-out, or when a refresh fails.
 */
export type SessionUser = { sub: string; name?: string; email?: string };

export type SessionRecord = {
  user: SessionUser;
  accessToken: string;
  /** Epoch milliseconds. */
  accessExpiresAt: number;
  refreshToken?: string;
  idToken?: string;
  createdAt: number;
  lastSeenAt: number;
};

export type TokenSet = {
  accessToken: string;
  /** Seconds until the access token expires. */
  expiresIn: number;
  refreshToken?: string;
  idToken?: string;
};

export type SessionDeps = {
  store: SessionStore;
  key: Buffer;
  idleSeconds: number;
  absoluteSeconds: number;
  now?: () => number;
};

/** Refresh the access token this long before it expires. */
const REFRESH_MARGIN_MS = 30_000;

function nowOf(deps: SessionDeps): number {
  return (deps.now ?? Date.now)();
}

function ttlSeconds(deps: SessionDeps, record: SessionRecord): number {
  const absoluteLeft = Math.ceil((record.createdAt + deps.absoluteSeconds * 1000 - nowOf(deps)) / 1000);
  return Math.max(1, Math.min(deps.idleSeconds, absoluteLeft));
}

async function write(deps: SessionDeps, id: string, record: SessionRecord): Promise<void> {
  await deps.store.set(storeKey(id), seal(record, deps.key), ttlSeconds(deps, record));
}

export async function createSession(deps: SessionDeps, user: SessionUser, tokens: TokenSet): Promise<string> {
  const now = nowOf(deps);
  const id = randomToken(32);
  await write(deps, id, {
    user,
    accessToken: tokens.accessToken,
    accessExpiresAt: now + tokens.expiresIn * 1000,
    refreshToken: tokens.refreshToken,
    idToken: tokens.idToken,
    createdAt: now,
    lastSeenAt: now,
  });
  return id;
}

/**
 * The live session for `id`, or null. An expired session (idle or absolute) is deleted. A live one
 * is touched, which restarts its idle timer, unless `touch` is false (status checks must not keep an
 * idle session alive).
 */
export async function readSession(
  deps: SessionDeps,
  id: string | undefined,
  { touch = true }: { touch?: boolean } = {},
): Promise<SessionRecord | null> {
  if (!id) return null;
  const record = unseal<SessionRecord>(await deps.store.get(storeKey(id)), deps.key);
  if (!record) return null;
  const now = nowOf(deps);
  const idleOver = now - record.lastSeenAt >= deps.idleSeconds * 1000;
  const absoluteOver = now - record.createdAt >= deps.absoluteSeconds * 1000;
  if (idleOver || absoluteOver) {
    await deps.store.delete(storeKey(id));
    return null;
  }
  if (!touch) return record;
  const touched = { ...record, lastSeenAt: now };
  await write(deps, id, touched);
  return touched;
}

export async function destroySession(deps: SessionDeps, id: string | undefined): Promise<SessionRecord | null> {
  if (!id) return null;
  const record = unseal<SessionRecord>(await deps.store.get(storeKey(id)), deps.key);
  await deps.store.delete(storeKey(id));
  return record;
}

/**
 * A usable access token for the session, refreshed shortly before it expires. If the refresh fails
 * (revoked, expired, Keycloak session ended) the session is removed and null is returned, so the
 * caller answers 401 and the user signs in again.
 */
export async function accessTokenFor(
  deps: SessionDeps,
  id: string,
  record: SessionRecord,
  refresh: (refreshToken: string) => Promise<TokenSet>,
): Promise<string | null> {
  if (record.accessExpiresAt - nowOf(deps) > REFRESH_MARGIN_MS) return record.accessToken;
  if (!record.refreshToken) {
    await deps.store.delete(storeKey(id));
    return null;
  }
  try {
    const tokens = await refresh(record.refreshToken);
    const updated: SessionRecord = {
      ...record,
      accessToken: tokens.accessToken,
      accessExpiresAt: nowOf(deps) + tokens.expiresIn * 1000,
      refreshToken: tokens.refreshToken ?? record.refreshToken,
      idToken: tokens.idToken ?? record.idToken,
    };
    await write(deps, id, updated);
    return updated.accessToken;
  } catch {
    await deps.store.delete(storeKey(id));
    return null;
  }
}
