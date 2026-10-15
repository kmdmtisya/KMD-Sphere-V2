import { redirect } from "next/navigation";

import { LiveMarkets } from "@/components/forex/LiveMarkets";
import { currentSession, forexEnabled } from "@/lib/server/auth/current";

export const metadata = { title: "Live markets · WealthSphere" };

/** Only where the forex module is on (DEC-23); otherwise the page is not there. */
export default async function LiveMarketsPage() {
  const session = await currentSession();
  if (!session || !(await forexEnabled(session))) redirect("/home");
  return <LiveMarkets />;
}
