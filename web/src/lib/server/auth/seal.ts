import "server-only";

import { createCipheriv, createDecipheriv, createHash, randomBytes, timingSafeEqual } from "node:crypto";

/**
 * Authenticated encryption (AES-256-GCM) for what the BFF keeps: session records in Redis and the
 * short-lived sign-in transaction cookie. A tampered or foreign value fails to open (null).
 */
const IV_BYTES = 12;
const TAG_BYTES = 16;

export function seal(value: unknown, key: Buffer): string {
  const iv = randomBytes(IV_BYTES);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const body = Buffer.concat([cipher.update(JSON.stringify(value), "utf8"), cipher.final()]);
  return Buffer.concat([iv, body, cipher.getAuthTag()]).toString("base64url");
}

export function unseal<T>(sealed: string | undefined | null, key: Buffer): T | null {
  if (!sealed) return null;
  try {
    const raw = Buffer.from(sealed, "base64url");
    if (raw.length <= IV_BYTES + TAG_BYTES) return null;
    const decipher = createDecipheriv("aes-256-gcm", key, raw.subarray(0, IV_BYTES));
    decipher.setAuthTag(raw.subarray(raw.length - TAG_BYTES));
    const plain = Buffer.concat([decipher.update(raw.subarray(IV_BYTES, raw.length - TAG_BYTES)), decipher.final()]);
    return JSON.parse(plain.toString("utf8")) as T;
  } catch {
    return null;
  }
}

/** A random, URL-safe token (session ids, CSRF tokens). */
export function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

/** Hashes a session id for use as a store key, so Redis never holds the cookie value itself. */
export function storeKey(sessionId: string): string {
  return `ws:web:session:${createHash("sha256").update(sessionId).digest("base64url")}`;
}

/** Constant-time string comparison (CSRF tokens). */
export function safeEqual(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}
