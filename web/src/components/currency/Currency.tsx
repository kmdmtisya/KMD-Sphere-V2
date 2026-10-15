"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/client/api";
import { formatMoney } from "@/lib/format/decimal";

import { Card } from "../cards/cards";
import { Button, SegmentedControl } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel, StaleChip } from "../figures/figures";
import {
  DisclosurePanel,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];

const STATUS: Record<S["ConvertOut"]["status"], string> = {
  current: "Current rate",
  cached: "Stored rate",
  stale: "Out-of-date rate",
  unavailable: "No rate available",
};
const CONCEPT: Record<S["ConvertOut"]["concept"], string> = {
  current_reporting: "Today's rate",
  historical_valuation: "The rate on that date",
  transaction: "The rate of the transaction",
};
const AMOUNT = /^\d{1,20}(\.\d{1,12})?$/;

/**
 * Reporting currency, converter, and FX status and history (P14-T14). Every rate and converted
 * amount is the backend's, shown as the decimal string it sent with its source, time and status.
 * A rate that is out of date or missing is labelled as such, never presented as current.
 */
export function Currency() {
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Currency
        </h1>
        <p className="text-fg-muted">
          Choose the currency your totals are shown in, convert an amount, and
          see where the exchange rates come from.
        </p>
      </header>
      <Reporting />
      <Converter />
      <Status />
      <History />
    </div>
  );
}

function useCurrencies() {
  return useQuery({
    queryKey: ["currencies"],
    queryFn: () => apiGet<S["CurrencyOut"][]>("currencies"),
    staleTime: 3_600_000,
  });
}

function CurrencySelect({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: string;
  onChange: (code: string) => void;
  hint?: string;
}) {
  const currencies = useCurrencies();
  return (
    <Field label={label} hint={hint}>
      {(p) => (
        <select {...p} value={value} onChange={(e) => onChange(e.target.value)}>
          {(currencies.data ?? [{ code: value, name: "" }]).map((c) => (
            <option key={c.code} value={c.code}>
              {c.code}
              {c.name ? ` · ${c.name}` : ""}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

function Reporting() {
  const queryClient = useQueryClient();
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<S["CurrencyPreferencesOut"]>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const [message, setMessage] = useState<string | null>(null);
  const change = useMutation({
    mutationFn: (code: string) =>
      apiPatch<S["CurrencyPreferencesOut"]>("me/currency-preferences", {
        reporting_currency: code,
      }),
    onSuccess: async () => {
      setMessage(null);
      // Every figure is shown in the reporting currency: refetch what depends on it.
      await queryClient.invalidateQueries();
    },
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The change was refused (${e.status}).`)
          : "The change could not be saved. Try again.",
      ),
  });
  if (prefs.isPending)
    return (
      <Card title="Reporting currency">
        <LoadingState label="Loading" lines={1} />
      </Card>
    );
  if (prefs.isError)
    return (
      <Card title="Reporting currency">
        <ErrorState
          message="Your currency setting could not be loaded."
          onRetry={() => void prefs.refetch()}
        />
      </Card>
    );
  return (
    <Card
      title="Reporting currency"
      info="Totals across portfolios are converted into this currency with the latest rates"
    >
      <div className="max-w-sm">
        <CurrencySelect
          label="Show my totals in"
          value={prefs.data.reporting_currency}
          onChange={(code) => change.mutate(code)}
          hint={
            prefs.data.is_default
              ? "This is the default; choose another to keep it for your account."
              : "Saved to your account, so it applies on every device."
          }
        />
      </div>
      {prefs.data.recent_currencies.length ? (
        <p className="mt-3 text-fg-muted">
          Recently used: {prefs.data.recent_currencies.join(", ")}
        </p>
      ) : null}
      {message ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
    </Card>
  );
}

function Converter() {
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<S["CurrencyPreferencesOut"]>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const [amount, setAmount] = useState("100");
  const [from, setFrom] = useState<string | null>(null);
  const [to, setTo] = useState("EUR");
  const [on, setOn] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const source = from ?? prefs.data?.reporting_currency ?? "USD";
  const today = new Date().toISOString().slice(0, 10);
  const valid = AMOUNT.test(amount);
  const convert = useMutation({
    mutationFn: () =>
      apiPost<S["ConvertOut"]>("fx/convert", {
        amount: { amount, currency: source },
        to,
        on: on || null,
      }),
    onMutate: () => setMessage(null),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The conversion was refused (${e.status}).`)
          : "The conversion could not be completed. Try again.",
      ),
  });
  const out = convert.data;
  return (
    <Card
      title="Converter"
      info="Uses the backend's stored exchange rates; nothing is calculated in the browser"
    >
      <form
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid && source !== to) convert.mutate();
        }}
      >
        <Field
          label="Amount"
          error={
            amount && !valid
              ? "Enter an amount using digits and a decimal point."
              : undefined
          }
        >
          {(p) => (
            <input
              {...p}
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          )}
        </Field>
        <CurrencySelect label="From" value={source} onChange={setFrom} />
        <CurrencySelect label="To" value={to} onChange={setTo} />
        <Field label="Rate of (optional)" hint="Leave blank for today's rate">
          {(p) => (
            <input
              {...p}
              type="date"
              max={today}
              value={on}
              onChange={(e) => setOn(e.target.value)}
            />
          )}
        </Field>
        <div className="flex items-end gap-2">
          <Button
            type="submit"
            variant="primary"
            disabled={!valid || source === to || convert.isPending}
          >
            {convert.isPending ? "Converting…" : "Convert"}
          </Button>
          <Button
            onClick={() => {
              setFrom(to);
              setTo(source);
            }}
          >
            Swap
          </Button>
        </div>
      </form>
      {source === to ? (
        <p className="mt-3 text-fg-muted">Choose two different currencies.</p>
      ) : null}
      {message ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {out ? (
        <div className="mt-4 flex flex-col gap-3" aria-live="polite">
          <p className="text-[length:var(--ws-font-size-title)] font-semibold tabular-nums">
            {formatMoney(out.source.amount, out.source.currency).text} ={" "}
            {formatMoney(out.converted.amount, out.converted.currency).text}
          </p>
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <Stat
              label="Rate"
              value={`1 ${out.source.currency} = ${out.rate} ${out.converted.currency}`}
            />
            <Stat label="Rate basis" value={CONCEPT[out.concept]} />
            <Stat label="Status" value={STATUS[out.status]} />
            <Stat label="Source" value={out.providers.join(", ") || "n/a"} />
            {out.path && out.path.length > 1 ? (
              <Stat label="Via" value={out.path.join(" → ")} />
            ) : null}
            {out.rate_timestamp ? (
              <Stat
                label="Rate time"
                value={
                  out.rate_timestamp.replace("T", " ").slice(0, 16) + " UTC"
                }
              />
            ) : null}
          </dl>
          {out.status === "stale" || out.status === "unavailable" ? (
            <StatusBanner kind="stale">
              This rate is not current. Do not rely on it for a decision that
              needs today&apos;s rate.
            </StatusBanner>
          ) : null}
          <DisclosurePanel
            title="About this conversion"
            notices={[
              out.notice ?? "Rates come from the providers named above.",
            ]}
          />
        </div>
      ) : null}
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {label}
      </dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Status() {
  const queryClient = useQueryClient();
  const status = useQuery({
    queryKey: ["fx-status"],
    queryFn: () => apiGet<S["FxStatusOut"]>("fx/status"),
    staleTime: 60_000,
  });
  const [message, setMessage] = useState<string | null>(null);
  const refresh = useMutation({
    mutationFn: () => apiPost<S["FxRefreshOut"]>("fx/refresh", {}),
    onMutate: () => setMessage(null),
    onSuccess: async (out) => {
      setMessage(
        out.refreshed
          ? "Rates were refreshed."
          : out.missing.length
            ? `No new rates for ${out.missing.join(", ")}.`
            : "Rates are already up to date.",
      );
      await queryClient.invalidateQueries({ queryKey: ["fx-status"] });
    },
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The refresh was refused (${e.status}).`)
          : "The refresh could not be completed.",
      ),
  });
  return (
    <Card
      title="Exchange-rate status"
      info="Each rate to your reporting currency, with where it came from and how old it is"
      actions={
        <Button disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? "Refreshing…" : "Refresh rates"}
        </Button>
      }
    >
      {status.isPending ? (
        <LoadingState label="Loading rates" lines={2} />
      ) : null}
      {status.isError ? (
        <ErrorState
          message="Rate status could not be loaded."
          onRetry={() => void status.refetch()}
        />
      ) : null}
      {message ? (
        <p role="status" className="mb-3 text-fg-muted">
          {message}
        </p>
      ) : null}
      {status.data ? (
        <>
          <p className="mb-3 flex items-center gap-2 text-fg-muted">
            Pivot currency {status.data.pivot_currency} ·{" "}
            <DataAsOfLabel asOf={status.data.checked_at} />
          </p>
          {status.data.rates.length === 0 ? (
            <p className="text-fg-muted">
              No exchange rates are needed for your accounts yet.
            </p>
          ) : (
            <DataGrid
              caption="Exchange-rate status"
              rowKey="currency"
              rows={status.data.rates.map((r) => ({
                currency: r.currency,
                rate: r.rate ?? "",
                status: STATUS[r.status],
                provider: r.provider ?? "",
                kind: r.rate_type ? r.rate_type.replace(/_/g, " ") : "",
                age:
                  r.age_seconds === null || r.age_seconds === undefined
                    ? ""
                    : r.age_seconds < 3600
                      ? `${Math.round(r.age_seconds / 60)} min`
                      : `${Math.round(r.age_seconds / 3600)} h`,
                stale:
                  r.status === "stale" || r.status === "unavailable"
                    ? "yes"
                    : "",
              }))}
              columns={[
                { key: "currency", header: "Currency" },
                { key: "rate", header: "Rate", align: "end" },
                {
                  key: "status",
                  header: "Status",
                  render: (r) =>
                    r.stale ? (
                      <span className="inline-flex items-center gap-1">
                        <StaleChip /> {r.status}
                      </span>
                    ) : (
                      <span>{r.status}</span>
                    ),
                },
                { key: "provider", header: "Provider" },
                { key: "kind", header: "Type" },
                { key: "age", header: "Age", align: "end" },
              ]}
            />
          )}
        </>
      ) : null}
    </Card>
  );
}

const RANGES = [
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
  { value: "365", label: "1 year" },
] as const;

function History() {
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<S["CurrencyPreferencesOut"]>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const [base, setBase] = useState("EUR");
  const [range, setRange] = useState<(typeof RANGES)[number]["value"]>("30");
  const quote = prefs.data?.reporting_currency ?? "USD";
  const end = new Date();
  const start = new Date(end.getTime() - Number(range) * 86_400_000);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const history = useQuery({
    queryKey: ["fx-history", base, quote, range],
    queryFn: () =>
      apiGet<S["FxHistoryOut"]>(
        `fx/history?base=${base}&quote=${quote}&start=${iso(start)}&end=${iso(end)}`,
      ),
    enabled: base !== quote && !!prefs.data,
    staleTime: 300_000,
  });
  return (
    <Card
      title="Rate history"
      info="Daily rates, with days that had no rate marked"
      actions={
        <SegmentedControl
          label="Period"
          options={RANGES}
          value={range}
          onChange={setRange}
        />
      }
    >
      <div className="mb-3 max-w-sm">
        <CurrencySelect
          label={`1 unit of … in ${quote}`}
          value={base}
          onChange={setBase}
        />
      </div>
      {base === quote ? (
        <p className="text-fg-muted">
          Choose a currency other than your reporting currency.
        </p>
      ) : null}
      {history.isPending && base !== quote ? (
        <LoadingState label="Loading history" lines={2} />
      ) : null}
      {history.isError ? (
        <ErrorState
          message="The history could not be loaded."
          onRetry={() => void history.refetch()}
        />
      ) : null}
      {history.data ? (
        <>
          {history.data.missing_days > 0 ? (
            <div className="mb-3">
              <StatusBanner kind="stale">
                {history.data.missing_days} day(s) in this period have no rate.
              </StatusBanner>
            </div>
          ) : null}
          <DataGrid
            caption="Rate history"
            rowKey="date"
            rows={[...history.data.points].reverse().map((p) => ({
              date: p.date,
              rate: p.rate ?? "",
              note: p.rate_missing
                ? "No rate"
                : p.from_earlier_day
                  ? "Carried from an earlier day"
                  : "",
              provider: p.provider ?? "",
            }))}
            columns={[
              { key: "date", header: "Date", kind: "date" },
              { key: "rate", header: `${base} in ${quote}`, align: "end" },
              { key: "note", header: "Note" },
              { key: "provider", header: "Provider" },
            ]}
          />
        </>
      ) : null}
    </Card>
  );
}
