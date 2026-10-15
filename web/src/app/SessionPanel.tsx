import { cookies } from "next/headers";

import { Button } from "@/components/controls/controls";
import { authRuntime, CSRF_COOKIE, SESSION_COOKIE } from "@/lib/server/auth/runtime";
import { readSession } from "@/lib/server/auth/session";

/**
 * Who is signed in, with sign-in and sign-out (P14-T05). The application shell (P14-T06) replaces
 * this with the profile menu. Sign-out is a plain form POST carrying the CSRF token.
 */
export async function SessionPanel() {
  const jar = await cookies();
  const id = jar.get(SESSION_COOKIE)?.value;
  let record = null;
  if (id) {
    try {
      record = await readSession(authRuntime().sessions, id, { touch: false });
    } catch {
      record = null;
    }
  }
  if (!record) {
    return (
      <a
        href="/api/auth/login"
        className="inline-flex min-h-9 w-fit items-center rounded-[var(--ws-radius-control)] bg-primary px-4 font-semibold text-on-primary"
      >
        Sign in
      </a>
    );
  }
  const who = record.user.name ?? record.user.email ?? "your account";
  return (
    <form method="post" action="/api/auth/logout" className="flex flex-wrap items-center gap-3">
      <p>
        Signed in as <strong data-testid="signed-in-as">{who}</strong>
      </p>
      <input type="hidden" name="csrf" value={jar.get(CSRF_COOKIE)?.value ?? ""} />
      <Button type="submit">Sign out</Button>
    </form>
  );
}
