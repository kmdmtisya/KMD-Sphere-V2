import {
  authRuntime,
  cookieFrom,
  SESSION_COOKIE,
} from "@/lib/server/auth/runtime";
import { readSession } from "@/lib/server/auth/session";

/**
 * Whether the browser has a live session, and who is signed in. Never returns a token. Reading it
 * does not extend the session (it is not user activity).
 */
export async function GET(request: Request) {
  const headers = { "Cache-Control": "no-store" };
  const id = cookieFrom(request, SESSION_COOKIE);
  if (!id) return Response.json({ signedIn: false }, { headers });
  let runtime;
  try {
    runtime = authRuntime();
  } catch {
    return Response.json({ signedIn: false }, { headers });
  }
  const record = await readSession(runtime.sessions, id, { touch: false });
  if (!record) return Response.json({ signedIn: false }, { headers });
  const { idleSeconds, absoluteSeconds } = runtime.settings;
  return Response.json(
    {
      signedIn: true,
      user: {
        name: record.user.name ?? null,
        email: record.user.email ?? null,
      },
      // Where the identity provider lets the user change their password and manage MFA (a link, never a token).
      accountUrl: `${runtime.settings.issuer.toString().replace(/\/$/, "")}/account`,
      expiresAt: {
        idle: new Date(record.lastSeenAt + idleSeconds * 1000).toISOString(),
        absolute: new Date(
          record.createdAt + absoluteSeconds * 1000,
        ).toISOString(),
      },
    },
    { headers },
  );
}
