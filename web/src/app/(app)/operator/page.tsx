import { redirect } from "next/navigation";

import { Operator } from "@/components/operator/Operator";
import { currentSession } from "@/lib/server/auth/current";

export const metadata = { title: "Operator views · WealthSphere" };

/** Only the support role sees this page; the API refuses everyone else regardless (DEC-34). */
export default async function OperatorPage() {
  const session = await currentSession();
  if (!session || !session.roles.includes("support")) redirect("/home");
  return <Operator />;
}
