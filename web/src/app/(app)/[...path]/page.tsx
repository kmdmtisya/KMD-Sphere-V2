import { notFound } from "next/navigation";

import { Card } from "@/components/cards/cards";
import { StatusBanner } from "@/components/states/states";
import { findNavItem } from "@/lib/nav/nav";

/**
 * A page of the portal that its task has not built yet (P14-T06). It names the task and the mobile
 * screen it answers and shows no figures: nothing is invented to fill the space.
 */
export default async function ModulePage({ params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const item = findNavItem(`/${path.join("/")}`);
  if (!item) notFound();
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">{item.label}</h1>
      <p className="text-fg-muted">{item.summary}</p>
      <Card title="Not built yet">
        <p>
          This page is built in <strong>{item.task}</strong>. The shell, sign-in and appearance around it are ready.
        </p>
        {item.mobile.length ? (
          <p className="mt-2 text-fg-muted">
            Mobile equivalent: {item.mobile.map((m) => (<code key={m} className="me-2">{m}</code>))}
          </p>
        ) : (
          <p className="mt-2 text-fg-muted">This capability is new on the web; no mobile screen exists yet.</p>
        )}
      </Card>
      <StatusBanner kind="info">No financial figures are shown here until the page is built.</StatusBanner>
    </div>
  );
}
