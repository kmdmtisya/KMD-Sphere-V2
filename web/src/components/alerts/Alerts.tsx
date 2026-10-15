"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import {
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  ApiError,
} from "@/lib/client/api";
import { formatMoney } from "@/lib/format/decimal";
import {
  ALERT_TYPES,
  alertRequest,
  emptyAlert,
  validateAlert,
  type AlertValues,
} from "@/lib/settings/alert-form";

import { Card } from "../cards/cards";
import { Button, SegmentedControl } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { StaleChip } from "../figures/figures";
import { AssetPicker } from "../portfolio/AssetPicker";
import { EmptyState, ErrorState, LoadingState } from "../states/states";

type S = components["schemas"];

const TABS = [
  { value: "notifications", label: "Notifications" },
  { value: "alerts", label: "Alerts" },
  { value: "watchlist", label: "Watchlist" },
] as const;
type Tab = (typeof TABS)[number]["value"];
const TYPE_LABEL = Object.fromEntries(
  ALERT_TYPES.map((t) => [t.value, t.label]),
);
const when = (iso: string) =>
  new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(iso));

/**
 * Notification centre, alerts and watchlist (P14-T16.3, T16.4). Alerts are evaluated by the
 * backend against the latest recorded prices; an alert tells you a level was crossed and is not a
 * recommendation to buy or sell.
 */
export function Alerts() {
  const [tab, setTab] = useState<Tab>("notifications");
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Alerts
          </h1>
          <p className="text-fg-muted">
            Notifications when a level you set is crossed, the alerts
            themselves, and the assets you are watching.
          </p>
        </div>
        <SegmentedControl
          label="Section"
          options={TABS}
          value={tab}
          onChange={setTab}
        />
      </header>
      {tab === "notifications" ? <Notifications /> : null}
      {tab === "alerts" ? <AlertList /> : null}
      {tab === "watchlist" ? <Watchlist /> : null}
    </div>
  );
}

function Notifications() {
  const queryClient = useQueryClient();
  const [unseenOnly, setUnseenOnly] = useState(false);
  const events = useQuery({
    queryKey: ["alert-events", { unseenOnly }],
    queryFn: () =>
      apiGet<S["AlertEventPage"]>(
        `alerts/events${unseenOnly ? "?unseen=true" : ""}`,
      ),
    staleTime: 15_000,
  });
  const seen = useMutation({
    mutationFn: (id: string) => apiPost(`alerts/events/${id}/seen`, {}),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["alert-events"] }),
  });
  return (
    <Card
      title="Notifications"
      actions={
        <label className="flex min-h-9 items-center gap-2">
          <input
            type="checkbox"
            checked={unseenOnly}
            onChange={(e) => setUnseenOnly(e.target.checked)}
          />
          Unseen only
        </label>
      }
    >
      {events.isPending ? (
        <LoadingState label="Loading notifications" lines={2} />
      ) : null}
      {events.isError ? (
        <ErrorState
          message="Notifications could not be loaded."
          onRetry={() => void events.refetch()}
        />
      ) : null}
      {events.data && events.data.items.length === 0 ? (
        <EmptyState title="Nothing to show">
          {unseenOnly
            ? "You have seen everything."
            : "No alert has been triggered yet."}
        </EmptyState>
      ) : null}
      {events.data && events.data.items.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {events.data.items.map((e) => (
            <li
              key={e.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--ws-radius-control)] border border-divider p-3"
            >
              <div>
                <p className={e.seen_at ? "" : "font-semibold"}>
                  {TYPE_LABEL[e.alert_type] ?? e.alert_type}: observed{" "}
                  {e.observed_value}
                </p>
                <p className="text-fg-muted">
                  Triggered {when(e.triggered_at)} · based on data from{" "}
                  {when(e.observed_as_of)}
                </p>
              </div>
              {e.seen_at ? (
                <span className="text-fg-muted">Seen</span>
              ) : (
                <Button
                  disabled={seen.isPending}
                  onClick={() => seen.mutate(e.id)}
                >
                  Mark as seen
                  <span className="sr-only">
                    {" "}
                    ({TYPE_LABEL[e.alert_type]}, {when(e.triggered_at)})
                  </span>
                </Button>
              )}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

function describe(a: S["AlertOut"]): string {
  if (a.alert_type === "allocation_above")
    return `${(a.asset_class ?? "").replace(/_/g, " ")} above ${a.threshold_percent}% of the portfolio`;
  const price = a.threshold_price
    ? formatMoney(a.threshold_price.amount, a.threshold_price.currency).text
    : "";
  return `${a.asset?.name ?? "Asset"} ${a.alert_type === "price_above" ? "above" : "below"} ${price}`;
}

function AlertList() {
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: () => apiGet<S["AlertOut"][]>("alerts"),
    staleTime: 30_000,
  });
  const change = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "active" | "paused" }) =>
      apiPatch(`alerts/${id}`, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiDelete(`alerts/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  return (
    <Card
      title="Your alerts"
      actions={
        <Button variant="primary" onClick={() => setCreating(true)}>
          New alert
        </Button>
      }
    >
      {alerts.isPending ? (
        <LoadingState label="Loading alerts" lines={2} />
      ) : null}
      {alerts.isError ? (
        <ErrorState
          message="Alerts could not be loaded."
          onRetry={() => void alerts.refetch()}
        />
      ) : null}
      {alerts.data && alerts.data.length === 0 ? (
        <EmptyState title="No alerts yet">
          Create an alert to be told when a price or an allocation crosses a
          level.
        </EmptyState>
      ) : null}
      {alerts.data && alerts.data.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {alerts.data.map((a) => (
            <li
              key={a.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--ws-radius-control)] border border-divider p-3"
            >
              <div>
                <p className="font-semibold">{describe(a)}</p>
                <p className="text-fg-muted">
                  {a.status === "triggered"
                    ? `Triggered ${a.triggered_at ? when(a.triggered_at) : ""}`
                    : a.status === "paused"
                      ? "Paused"
                      : "Active"}
                  {a.note ? ` · ${a.note}` : ""}
                </p>
              </div>
              <div className="flex gap-2">
                {a.status !== "triggered" ? (
                  <Button
                    disabled={change.isPending}
                    onClick={() =>
                      change.mutate({
                        id: a.id,
                        status: a.status === "paused" ? "active" : "paused",
                      })
                    }
                  >
                    {a.status === "paused" ? "Resume" : "Pause"}
                    <span className="sr-only"> {describe(a)}</span>
                  </Button>
                ) : null}
                <Button
                  variant="ghost"
                  disabled={remove.isPending}
                  onClick={() => remove.mutate(a.id)}
                >
                  Delete<span className="sr-only"> {describe(a)}</span>
                </Button>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <AlertDrawer open={creating} onClose={() => setCreating(false)} />
    </Card>
  );
}

function AlertDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Drawer open={open} title="New alert" onClose={onClose}>
      {open ? <AlertForm onDone={onClose} /> : null}
    </Drawer>
  );
}

function AlertForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<AlertValues>(emptyAlert);
  const [assetName, setAssetName] = useState("");
  const [problems, setProblems] = useState<ReturnType<typeof validateAlert>>(
    {},
  );
  const [message, setMessage] = useState<string | null>(null);
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  const classes = useQuery({
    queryKey: ["asset-classes"],
    queryFn: () => apiGet<S["AssetClassOut"][]>("asset-classes"),
    staleTime: 3_600_000,
  });
  const set = <K extends keyof AlertValues>(key: K, value: AlertValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
  const help = ALERT_TYPES.find((t) => t.value === values.type)?.help;
  const save = useMutation({
    mutationFn: () => apiPost("alerts", alertRequest(values)),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["alerts"] });
      onDone();
    },
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The alert was refused (${e.status}).`)
          : "The alert could not be saved. Try again.",
      ),
  });

  async function chooseAsset(asset: { id: string; name: string } | null) {
    set("assetId", asset?.id ?? "");
    setAssetName(asset?.name ?? "");
    if (asset) {
      try {
        const full = await apiGet<S["AssetOut"]>(`assets/${asset.id}`);
        set("currency", full.currency);
      } catch {
        set("currency", "");
      }
    }
  }
  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateAlert(values);
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0) save.mutate();
  }
  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Alert me when" hint={help}>
        {(p) => (
          <select
            {...p}
            value={values.type}
            onChange={(e) => set("type", e.target.value as AlertValues["type"])}
          >
            {ALERT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      {values.type === "allocation_above" ? (
        <>
          <Field label="Portfolio" error={problems.portfolioId}>
            {(p) => (
              <select
                {...p}
                value={values.portfolioId}
                onChange={(e) => set("portfolioId", e.target.value)}
              >
                <option value="">Choose…</option>
                {(portfolios.data ?? []).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Asset class" error={problems.assetClass}>
            {(p) => (
              <select
                {...p}
                value={values.assetClass}
                onChange={(e) => set("assetClass", e.target.value)}
              >
                <option value="">Choose…</option>
                {(classes.data ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Share of the portfolio (%)" error={problems.percent}>
            {(p) => (
              <input
                {...p}
                inputMode="decimal"
                value={values.percent}
                onChange={(e) => set("percent", e.target.value)}
              />
            )}
          </Field>
        </>
      ) : (
        <>
          <AssetPicker
            value={values.assetId}
            selectedName={assetName}
            error={problems.assetId}
            onChange={(a) => void chooseAsset(a)}
          />
          <Field
            label={`Price${values.currency ? ` (${values.currency})` : ""}`}
            error={problems.price ?? problems.currency}
          >
            {(p) => (
              <input
                {...p}
                inputMode="decimal"
                value={values.price}
                onChange={(e) => set("price", e.target.value)}
              />
            )}
          </Field>
        </>
      )}
      <Field label="Note (optional)" error={problems.note}>
        {(p) => (
          <input
            {...p}
            maxLength={200}
            value={values.note}
            onChange={(e) => set("note", e.target.value)}
          />
        )}
      </Field>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Saving…" : "Create the alert"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

function Watchlist() {
  const queryClient = useQueryClient();
  const [picked, setPicked] = useState<{ id: string; name: string } | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => apiGet<S["WatchlistItemOut"][]>("watchlist"),
    staleTime: 30_000,
  });
  const add = useMutation({
    mutationFn: (assetId: string) =>
      apiPost("watchlist", { asset_id: assetId }),
    onMutate: () => setMessage(null),
    onSuccess: async () => {
      setPicked(null);
      await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `Could not add it (${e.status}).`)
          : "Could not add it. Try again.",
      ),
  });
  const remove = useMutation({
    mutationFn: (assetId: string) => apiDelete(`watchlist/${assetId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["watchlist"] }),
  });
  return (
    <Card title="Watchlist" info="Assets you follow without holding them">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <AssetPicker
            label="Add an asset"
            value={picked?.id ?? ""}
            selectedName={picked?.name}
            onChange={setPicked}
          />
        </div>
        <Button
          variant="primary"
          disabled={!picked || add.isPending}
          onClick={() => picked && add.mutate(picked.id)}
        >
          Add to watchlist
        </Button>
      </div>
      {message ? (
        <p role="alert" className="mb-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {list.isPending ? (
        <LoadingState label="Loading the watchlist" lines={2} />
      ) : null}
      {list.isError ? (
        <ErrorState
          message="The watchlist could not be loaded."
          onRetry={() => void list.refetch()}
        />
      ) : null}
      {list.data && list.data.length === 0 ? (
        <EmptyState title="Nothing watched yet">
          Add an asset above to follow its latest price.
        </EmptyState>
      ) : null}
      {list.data && list.data.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {list.data.map((w) => (
            <li
              key={w.asset.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--ws-radius-control)] border border-divider p-3"
            >
              <div>
                <p className="font-semibold">
                  {w.asset.name}
                  {w.asset.symbol ? ` (${w.asset.symbol})` : ""}
                </p>
                <p className="flex items-center gap-2 text-fg-muted">
                  {w.latest_price ? (
                    <>
                      <span className="tabular-nums">
                        {
                          formatMoney(
                            w.latest_price.price,
                            w.latest_price.currency,
                          ).text
                        }
                      </span>
                      <span>
                        as of {when(w.latest_price.as_of)} ·{" "}
                        {w.latest_price.provider}
                      </span>
                      {w.latest_price.stale ? <StaleChip /> : null}
                    </>
                  ) : (
                    "No price recorded yet"
                  )}
                </p>
              </div>
              <Button
                variant="ghost"
                disabled={remove.isPending}
                onClick={() => remove.mutate(w.asset.id)}
              >
                Remove<span className="sr-only"> {w.asset.name}</span>
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
