/**
 * Forex notices (P14-T24.5): the same in-app notices as the mobile app. Which ones the person wants
 * is a per-browser preference; the notices come from data the workspace already loads (the calendar
 * and the paper positions). Nothing here is calculated money: only dates are compared.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];

export type NoticePrefs = { eventReminders: boolean; paperExits: boolean };
export const DEFAULT_PREFS: NoticePrefs = { eventReminders: true, paperExits: true };
export const NOTICES_KEY = "ws.forex.notices";

export type Notice =
  | { kind: "event"; id: string; name: string; currencies: string[]; minutes: number }
  | { kind: "paper"; id: string; instrument: string; reason: string | null; exitAt: string };

export function decodePrefs(raw: string | null): NoticePrefs {
  if (!raw) return DEFAULT_PREFS;
  try {
    const m = JSON.parse(raw) as Record<string, unknown>;
    return { eventReminders: m.eventReminders !== false, paperExits: m.paperExits !== false };
  } catch {
    return DEFAULT_PREFS;
  }
}

export const encodePrefs = (p: NoticePrefs) => JSON.stringify(p);

const MINUTE = 60_000;

/** High-importance events starting within `eventWindowMin`, and paper positions closed within `closedWindowH` hours. */
export function noticesFor(input: {
  prefs: NoticePrefs;
  events: S["EventOut"][];
  positions: S["ForexPaperPositionOut"][];
  now: Date;
  eventWindowMin?: number;
  closedWindowH?: number;
}): Notice[] {
  const { prefs, events, positions, now } = input;
  const eventWindow = (input.eventWindowMin ?? 60) * MINUTE;
  const closedWindow = (input.closedWindowH ?? 24) * 60 * MINUTE;
  const out: Notice[] = [];
  if (prefs.eventReminders) {
    for (const e of events) {
      const until = new Date(e.scheduled_at).getTime() - now.getTime();
      if (e.importance === "high" && until >= 0 && until <= eventWindow)
        out.push({ kind: "event", id: e.id, name: e.name, currencies: e.currencies, minutes: Math.floor(until / MINUTE) });
    }
  }
  if (prefs.paperExits) {
    for (const p of positions) {
      if (!p.exit_at) continue;
      const age = now.getTime() - new Date(p.exit_at).getTime();
      if (age >= 0 && age <= closedWindow)
        out.push({ kind: "paper", id: p.id, instrument: p.instrument, reason: p.exit_reason, exitAt: p.exit_at });
    }
  }
  return out;
}
