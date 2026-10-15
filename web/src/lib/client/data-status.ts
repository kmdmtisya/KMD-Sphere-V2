/** The data-status chip (P14-T06): the weakest status among the rates the API reports (/fx/status). */
export type RateStatus = "current" | "cached" | "stale" | "unavailable";
export type DataStatus = { kind: "current" | "delayed" | "stale" | "unknown"; label: string };

export function dataStatus(rates: { status: string }[] | undefined): DataStatus {
  if (!rates || rates.length === 0) return { kind: "unknown", label: "Data status unknown" };
  const statuses = new Set(rates.map((r) => r.status));
  if (statuses.has("unavailable") || statuses.has("stale")) return { kind: "stale", label: "Data: stale" };
  if (statuses.has("cached")) return { kind: "delayed", label: "Data: delayed" };
  return { kind: "current", label: "Data: current" };
}
