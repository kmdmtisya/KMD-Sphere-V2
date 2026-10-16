"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";
import { useStored } from "@/lib/client/local-storage";
import {
  decodePrefs,
  encodePrefs,
  noticesFor,
  NOTICES_KEY,
} from "@/lib/forex/notices";

import { Card } from "../cards/cards";

type S = components["schemas"];

/**
 * Forex notices (P14-T24.5): a high-importance event about to start, and a paper position that has
 * just closed. They come from the calendar and the paper account the workspace already reads, and
 * which ones to show is remembered in this browser only. They are reminders, not advice or signals.
 */
export function Notices() {
  const [raw, setRaw] = useStored(NOTICES_KEY);
  const prefs = useMemo(() => decodePrefs(raw), [raw]);
  const events = useQuery({
    queryKey: ["forex-notice-events"],
    queryFn: () => {
      const start = new Date();
      const end = new Date(start.getTime() + 2 * 3_600_000);
      return apiGet<S["CalendarOut"]>(
        `forex/calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&min_importance=high`,
      );
    },
    staleTime: 60_000,
    refetchInterval: 60_000,
  });
  const accounts = useQuery({
    queryKey: ["paper-accounts"],
    queryFn: () => apiGet<S["ForexPaperAccountsOut"]>("forex/paper/accounts"),
    staleTime: 15_000,
  });
  const accountId = accounts.data?.items[0]?.id;
  const positions = useQuery({
    queryKey: ["paper-positions", accountId],
    enabled: !!accountId,
    queryFn: () =>
      apiGet<S["ForexPaperPositionsOut"]>(
        `forex/paper/accounts/${accountId}/positions`,
      ),
    staleTime: 10_000,
  });
  // The clock only matters when the data arrives, so notices are worked out then.
  const notices = useMemo(
    () =>
      noticesFor({
        prefs,
        events: events.data?.items ?? [],
        positions: positions.data?.items ?? [],
        now: new Date(),
      }),
    [prefs, events.data, positions.data],
  );
  const toggle = (key: "eventReminders" | "paperExits") =>
    setRaw(encodePrefs({ ...prefs, [key]: !prefs[key] }));
  return (
    <Card
      title="Notices"
      info="Reminders from your calendar and your paper account. Remembered in this browser only"
    >
      <div className="flex flex-wrap gap-4">
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={prefs.eventReminders}
            onChange={() => toggle("eventReminders")}
          />
          Remind me of high-impact events in the next hour
        </label>
        <label className="inline-flex items-center gap-2">
          <input
            type="checkbox"
            checked={prefs.paperExits}
            onChange={() => toggle("paperExits")}
          />
          Tell me when a paper position closes
        </label>
      </div>
      <ul className="mt-3 flex flex-col gap-1" aria-label="Current notices">
        {notices.length === 0 ? (
          <li className="text-fg-muted">Nothing needs your attention now.</li>
        ) : null}
        {notices.map((n) =>
          n.kind === "event" ? (
            <li key={`e-${n.id}`}>
              <strong>{n.name}</strong> ({n.currencies.join(", ")}) starts in{" "}
              {n.minutes} min. Prices often move around releases; this is a
              reminder, not a signal.
            </li>
          ) : (
            <li key={`p-${n.id}`}>
              Paper trading · simulated money: your {n.instrument.replace("_", "/")}{" "}
              position closed
              {n.reason ? ` (${n.reason})` : ""}.
            </li>
          ),
        )}
      </ul>
    </Card>
  );
}
