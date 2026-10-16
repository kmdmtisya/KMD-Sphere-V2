import { redirect } from "next/navigation";

import { Workspace } from "@/components/forex/Workspace";
import { currentSession, forexEnabled } from "@/lib/server/auth/current";

export const metadata = { title: "Forex workspace · WealthSphere" };

/** Only where the forex module is on (DEC-23); otherwise the page is not there. */
export default async function WorkspacePage() {
  const session = await currentSession();
  if (!session || !(await forexEnabled(session))) redirect("/home");
  return <Workspace />;
}
