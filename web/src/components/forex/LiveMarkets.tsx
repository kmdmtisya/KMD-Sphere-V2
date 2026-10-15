"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost } from "@/lib/client/api";
import { useStored } from "@/lib/client/local-storage";
import {
  createStream,
  emptyState,
  type ConnectionStatus,
  type StreamState,
} from "@/lib/forex/stream";

import { Card } from "../cards/cards";
import { DataGrid } from "../data/DataGrid";
import { SimulatedBadge, StaleChip } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];

const SELECTED_KEY = "ws.forex.pairs";
const DEFAULT_PAIRS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD"];

const CONNECTION: Record<ConnectionStatus, string> = {
  connecting: "Connecting to live quotes…",
  live: "Live quotes connected.",
  reconnecting: "The connection dropped. Reconnecting…",
  unavailable: "Live quotes are not available right now.",
  stopped: "Live quotes are paused.",
};
const FEED = {
  connected: "Feed connected",
  degraded: "Feed degraded: quotes may be late",
  disconnected: "Feed disconnected: quotes are not current",
} as const;

const fetchStreamUrl = async () =>
  (await apiGet<{ url: string }>("forex/stream-url")).url;
const mintTicket = async () =>
  (await apiPost<{ ticket: string }>("forex/stream-ticket", {})).ticket;

/**
 * Live markets (P14-T13.3), shown only where the forex module is on (DEC-23). Quotes arrive over a
 * WebSocket authorised by a single-use ticket; the access token never reaches the browser. Every
 * quote is labelled with its data type and freshness: a simulated or stale quote is never shown as
 * a live market, and the page places no trades and gives no advice.
 */
export function LiveMarkets() {
  const instruments = useQuery({
    queryKey: ["forex-instruments"],
    queryFn: () => apiGet<S["InstrumentsOut"]>("forex/instruments"),
    staleTime: 300_000,
  });
  const [stored, setStored] = useStored(SELECTED_KEY);
  const codes = useMemo(
    () => (instruments.data?.items ?? []).map((i) => i.code),
    [instruments.data],
  );
  const selected = useMemo(() => {
    const wanted = stored ? stored.split(",").filter(Boolean) : DEFAULT_PAIRS;
    const known = wanted.filter((p) => codes.includes(p));
    return known.length ? known : codes.slice(0, 4);
  }, [stored, codes]);

  const [state, setState] = useState<StreamState>(emptyState);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const wanted = useRef<string[]>([]);
  const followed = useRef<string[]>([]);
  const stream = useRef<ReturnType<typeof createStream> | null>(null);

  useEffect(() => {
    wanted.current = selected;
  }, [selected]);

  // One connection while the page is open and the list of pairs is known.
  const ready = codes.length > 0;
  useEffect(() => {
    if (!ready) return;
    const s = createStream({
      instruments: () => {
        followed.current = wanted.current;
        return wanted.current;
      },
      onChange: (next, st) => {
        setState(next);
        setStatus(st);
      },
      streamUrl: fetchStreamUrl,
      mintTicket,
    });
    stream.current = s;
    s.start();
    return () => {
      s.stop();
      stream.current = null;
    };
  }, [ready]);

  // Follow changes to the chosen pairs on the open connection.
  useEffect(() => {
    if (status !== "live") return;
    stream.current?.follow(selected, followed.current);
    followed.current = selected;
  }, [selected, status]);

  if (instruments.isPending)
    return <LoadingState label="Loading instruments" />;
  if (instruments.isError)
    return (
      <ErrorState
        message="The instruments could not be loaded."
        onRetry={() => void instruments.refetch()}
      />
    );

  const toggle = (code: string) =>
    setStored(
      (selected.includes(code)
        ? selected.filter((c) => c !== code)
        : [...selected, code]
      ).join(","),
    );
  const rows = selected.map((code) => {
    const q = state.quotes[code];
    return {
      id: code,
      pair: code.replace("_", "/"),
      bid: q?.bid ?? "",
      ask: q?.ask ?? "",
      mid: q?.mid ?? "",
      freshness: q
        ? q.freshness === "fresh"
          ? "Fresh"
          : q.freshness === "stale"
            ? "Stale"
            : "Unavailable"
        : "Waiting",
      kind: q?.data_type ? q.data_type.replace(/_/g, " ") : "",
      age:
        q?.age_seconds !== null && q?.age_seconds !== undefined
          ? `${q.age_seconds}s`
          : "",
      currency: "",
    };
  });
  const anySimulated = Object.values(state.quotes).some((q) =>
    (q.data_type ?? "").includes("simulated"),
  );

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Live markets
          </h1>
          <p className="text-fg-muted">
            Quotes for the pairs you follow, labelled by data type and
            freshness. This page places no trades and gives no advice.
          </p>
        </div>
        {anySimulated ? <SimulatedBadge /> : null}
      </header>
      <StatusBanner
        kind={
          status === "live" && state.feed === "connected" ? "info" : "stale"
        }
      >
        <span role="status">
          {CONNECTION[status]}
          {state.feed ? ` ${FEED[state.feed]}.` : ""}
        </span>
      </StatusBanner>
      {state.lastError ? (
        <p role="alert" className="font-semibold text-negative-text">
          {state.lastError}
        </p>
      ) : null}

      <Card
        title="Pairs you follow"
        info={
          state.maxInstruments
            ? `Up to ${state.maxInstruments} on one connection`
            : undefined
        }
      >
        <fieldset>
          <legend className="sr-only">Choose the pairs to follow</legend>
          <ul className="grid gap-2 sm:grid-cols-3 lg:grid-cols-6">
            {instruments.data.items.map((i) => (
              <li key={i.code}>
                <label className="flex min-h-9 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={selected.includes(i.code)}
                    onChange={() => toggle(i.code)}
                  />
                  {i.base}/{i.quote}
                </label>
              </li>
            ))}
          </ul>
        </fieldset>
      </Card>

      {selected.length === 0 ? (
        <EmptyState title="No pairs chosen">
          Choose at least one pair above to see its quote.
        </EmptyState>
      ) : (
        <Card title="Quotes">
          <DataGrid
            caption="Live quotes"
            rowKey="id"
            rows={rows}
            columns={[
              { key: "pair", header: "Pair" },
              { key: "bid", header: "Bid", align: "end" },
              { key: "ask", header: "Ask", align: "end" },
              { key: "mid", header: "Mid", align: "end" },
              {
                key: "freshness",
                header: "Freshness",
                render: (r) =>
                  r.freshness === "Stale" ? (
                    <StaleChip />
                  ) : (
                    <span>{r.freshness}</span>
                  ),
              },
              { key: "kind", header: "Data type" },
              { key: "age", header: "Age", align: "end" },
            ]}
          />
        </Card>
      )}
      <DisclosurePanel
        title="About these quotes"
        notices={[
          state.notice ?? instruments.data.notice,
          "Prices are shown as received. A simulated feed is not a real market; a stale quote is not current.",
        ]}
      />
    </div>
  );
}
