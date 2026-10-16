import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api";

import { decodePrefs, DEFAULT_PREFS, encodePrefs, noticesFor } from "./notices";

type S = components["schemas"];
const now = new Date("2026-10-16T10:00:00Z");
const ev = (id: string, importance: "low" | "medium" | "high", at: string) =>
  ({
    id,
    name: `Event ${id}`,
    importance,
    scheduled_at: at,
    currencies: ["USD"],
  }) as unknown as S["EventOut"];
const pos = (id: string, exit: string | null) =>
  ({
    id,
    instrument: "EUR_USD",
    exit_at: exit,
    exit_reason: "stop",
  }) as unknown as S["ForexPaperPositionOut"];

describe("forex notices", () => {
  it("reminds only of high-importance events that start within the hour", () => {
    const out = noticesFor({
      prefs: DEFAULT_PREFS,
      now,
      positions: [],
      events: [
        ev("soon", "high", "2026-10-16T10:30:00Z"),
        ev("later", "high", "2026-10-16T11:30:00Z"),
        ev("minor", "medium", "2026-10-16T10:10:00Z"),
        ev("past", "high", "2026-10-16T09:50:00Z"),
      ],
    });
    expect(out.map((n) => n.id)).toEqual(["soon"]);
    expect(out[0]).toMatchObject({ kind: "event", minutes: 30 });
  });

  it("tells of paper positions closed in the last day, not open or older ones", () => {
    const out = noticesFor({
      prefs: DEFAULT_PREFS,
      now,
      events: [],
      positions: [
        pos("fresh", "2026-10-16T08:00:00Z"),
        pos("old", "2026-10-14T08:00:00Z"),
        pos("open", null),
      ],
    });
    expect(out.map((n) => n.id)).toEqual(["fresh"]);
  });

  it("respects what the person turned off", () => {
    const input = {
      now,
      events: [ev("soon", "high", "2026-10-16T10:30:00Z")],
      positions: [pos("fresh", "2026-10-16T08:00:00Z")],
    };
    expect(
      noticesFor({
        ...input,
        prefs: { eventReminders: false, paperExits: true },
      }).map((n) => n.kind),
    ).toEqual(["paper"]);
    expect(
      noticesFor({
        ...input,
        prefs: { eventReminders: true, paperExits: false },
      }).map((n) => n.kind),
    ).toEqual(["event"]);
  });

  it("reads and writes the saved choice, and falls back to both on when it is missing or damaged", () => {
    expect(decodePrefs(null)).toEqual(DEFAULT_PREFS);
    expect(decodePrefs("not json")).toEqual(DEFAULT_PREFS);
    expect(
      decodePrefs(encodePrefs({ eventReminders: false, paperExits: true })),
    ).toEqual({ eventReminders: false, paperExits: true });
  });
});
