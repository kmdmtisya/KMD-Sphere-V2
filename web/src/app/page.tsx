import { Suspense } from "react";

import { AppearanceSelector, ThemeCycleButton } from "@/components/theme/appearance";

import { SessionPanel } from "./SessionPanel";

export default function Home() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-3xl flex-col justify-center gap-4 px-6">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-3xl font-semibold">WealthSphere</h1>
        <ThemeCycleButton />
      </div>
      <p className="text-fg-muted">
        Web portal foundation. The dashboard and the rest of the portal arrive with the next steps; no
        financial data is shown here yet.
      </p>
      <Suspense fallback={<p className="text-fg-muted">Checking your session…</p>}>
        <SessionPanel />
      </Suspense>
      <AppearanceSelector />
    </main>
  );
}
