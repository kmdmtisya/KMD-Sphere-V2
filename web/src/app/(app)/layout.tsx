import { redirect } from "next/navigation";
import { Suspense } from "react";

import { LoadingState } from "@/components/states/states";
import { Shell } from "@/components/shell/Shell";
import { accountOf, currentSession, forexEnabled } from "@/lib/server/auth/current";
import { visibleNav } from "@/lib/nav/nav";

/**
 * The signed-in area (P14-T06): requires a session (otherwise back to the landing page, which
 * offers sign-in), then shows the application shell. The navigation is built here from what the
 * server knows: the forex module flag and the user's roles. The API still enforces every permission.
 */
async function SignedIn({ children }: { children: React.ReactNode }) {
  const session = await currentSession();
  if (!session) redirect("/");
  const [forex, account] = await Promise.all([forexEnabled(session), accountOf(session)]);
  const groups = visibleNav({ forex, support: session.roles.includes("support") });
  return (
    <Shell groups={groups} user={account}>
      {children}
    </Shell>
  );
}

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <main className="p-6">
          <LoadingState label="Loading your portal" />
        </main>
      }
    >
      <SignedIn>{children}</SignedIn>
    </Suspense>
  );
}
