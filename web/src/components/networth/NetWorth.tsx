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
  emptyLiability,
  LIABILITY_TYPES,
  liabilityFromApi,
  liabilityRequest,
  validateLiability,
  type LiabilityValues,
} from "@/lib/networth/liability-form";

import { rangeParams } from "../analytics/Analytics";
import { Card, KpiCard } from "../cards/cards";
import { AllocationDonutChart } from "../charts/AllocationDonutChart";
import { PerformanceLineChart } from "../charts/PerformanceLineChart";
import { Button, SegmentedControl } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];
type Liability = S["LiabilityOut"];

const RANGES = [
  { value: "1Y", label: "1Y" },
  { value: "5Y", label: "5Y" },
  { value: "ALL", label: "All" },
] as const;
type Range = (typeof RANGES)[number]["value"];
const TYPE_LABEL = Object.fromEntries(
  LIABILITY_TYPES.map((t) => [t.value, t.label]),
);

/**
 * Net worth and liabilities (P14-T11.1): what you own, what you owe and what is left, with the
 * history from the backend. Every figure is the server's; the page only shows and edits records.
 */
export function NetWorth() {
  const [range, setRange] = useState<Range>("1Y");
  const [editing, setEditing] = useState<Liability | "new" | null>(null);
  const nw = useQuery({
    queryKey: ["net-worth"],
    queryFn: () => apiGet<S["NetWorthOut"]>("net-worth"),
    staleTime: 60_000,
  });
  const liabilities = useQuery({
    queryKey: ["liabilities"],
    queryFn: () => apiGet<Liability[]>("liabilities"),
    staleTime: 30_000,
  });

  if (nw.isPending) return <LoadingState label="Loading net worth" />;
  if (nw.isError)
    return (
      <ErrorState
        message="Net worth could not be loaded."
        onRetry={() => void nw.refetch()}
      />
    );
  const n = nw.data;
  const f = n.freshness;
  const noData =
    n.assets_by_class.length === 0 && n.liability_lines.length === 0;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Net worth
          </h1>
          <p className="text-fg-muted">
            What you own, what you owe and what is left, in {n.currency}.
          </p>
        </div>
        <DataAsOfLabel asOf={n.as_of} />
      </header>

      {!f.complete ? (
        <StatusBanner kind="stale">
          Some figures are incomplete: {f.unpriced_assets} asset(s) have no
          price
          {f.unconverted_currencies.length
            ? `, and no exchange rate for ${f.unconverted_currencies.join(", ")}`
            : ""}
          . They are left out of the totals.
        </StatusBanner>
      ) : null}
      {f.stale_fx.length ? (
        <StatusBanner kind="stale">
          The exchange rate for {f.stale_fx.join(", ")} is out of date.
        </StatusBanner>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          label="Net worth"
          value={n.net_worth.amount}
          currency={n.currency}
          info="Assets minus liabilities"
        />
        <KpiCard
          label="Assets"
          value={n.assets.amount}
          currency={n.currency}
          info="Your active portfolios"
        />
        <KpiCard
          label="Liabilities"
          value={n.liabilities.amount}
          currency={n.currency}
          info="What you owe, as last recorded"
        />
      </div>

      {noData ? (
        <EmptyState title="Nothing to show yet">
          Add a portfolio with some holdings, or record a liability, to see your
          net worth.
        </EmptyState>
      ) : null}

      <History range={range} onRange={setRange} />

      {n.assets_by_class.length ? (
        <AllocationDonutChart
          title="Assets by class"
          currency={n.currency}
          items={n.assets_by_class.map((s) => ({
            label: s.asset_class.replace(/_/g, " "),
            percent: s.share_percent ?? "0",
            amount: s.value.amount,
          }))}
          summary={`Assets by class: ${n.assets_by_class.map((s) => `${s.asset_class.replace(/_/g, " ")} ${formatMoney(s.value.amount, n.currency).text}`).join(", ")}.`}
        />
      ) : null}

      <Card
        title="Liabilities"
        info="Balances are the figures you entered, with the date each applied"
        actions={
          <Button variant="primary" onClick={() => setEditing("new")}>
            Add a liability
          </Button>
        }
      >
        {liabilities.isPending ? (
          <LoadingState label="Loading liabilities" lines={2} />
        ) : null}
        {liabilities.isError ? (
          <ErrorState
            message="Liabilities could not be loaded."
            onRetry={() => void liabilities.refetch()}
          />
        ) : null}
        {liabilities.data && liabilities.data.length === 0 ? (
          <p className="text-fg-muted">You have recorded no liabilities.</p>
        ) : null}
        {liabilities.data && liabilities.data.length > 0 ? (
          <DataGrid
            caption="Liabilities"
            rowKey="id"
            rows={liabilities.data.map((l) => ({
              id: l.id,
              name: l.name,
              type: TYPE_LABEL[l.liability_type],
              balance: l.balance.amount,
              currency: l.balance.currency,
              asOf: l.balance_as_of,
              rate: l.interest_rate_percent
                ? `${l.interest_rate_percent}%`
                : "",
            }))}
            columns={[
              { key: "name", header: "Name" },
              { key: "type", header: "Type" },
              {
                key: "balance",
                header: "Balance",
                kind: "money",
                currencyKey: "currency",
              },
              { key: "asOf", header: "As of", kind: "date" },
              { key: "rate", header: "Interest", align: "end" },
              {
                key: "id",
                header: "Actions",
                render: (row) => (
                  <Button
                    variant="ghost"
                    onClick={() =>
                      setEditing(
                        liabilities.data.find((l) => l.id === row.id) ?? null,
                      )
                    }
                  >
                    Edit<span className="sr-only"> {row.name}</span>
                  </Button>
                ),
              },
            ]}
          />
        ) : null}
      </Card>
      <DisclosurePanel
        title="About net worth"
        notices={[
          "Net worth is your active portfolios' value minus the liabilities you recorded, converted at the latest exchange rates. It is a snapshot of recorded figures, not a valuation or advice.",
        ]}
      />
      <LiabilityDrawer
        editing={editing}
        currency={n.currency}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}

function History({
  range,
  onRange,
}: {
  range: Range;
  onRange: (r: Range) => void;
}) {
  const params = rangeParams(range, new Date());
  const frequency = range === "1Y" ? "monthly" : params.frequency;
  const history = useQuery({
    queryKey: ["net-worth-history", range],
    queryFn: () =>
      apiGet<S["NetWorthHistoryOut"]>(
        `net-worth/history?frequency=${frequency}${params.start ? `&start=${params.start}` : ""}`,
      ),
    staleTime: 60_000,
  });
  const picker = (
    <SegmentedControl
      label="Period"
      options={RANGES}
      value={range}
      onChange={onRange}
    />
  );
  if (history.isPending)
    return (
      <Card title="Net worth over time" actions={picker}>
        <LoadingState label="Loading the history" />
      </Card>
    );
  if (history.isError)
    return (
      <Card title="Net worth over time" actions={picker}>
        <ErrorState
          message="The history could not be loaded."
          onRetry={() => void history.refetch()}
        />
      </Card>
    );
  const h = history.data;
  if (h.points.length < 2) {
    return (
      <Card title="Net worth over time" actions={picker}>
        <EmptyState title="Not enough history">
          Net worth over time appears once your portfolios or liabilities cover
          at least two dates.
        </EmptyState>
      </Card>
    );
  }
  const last = h.points[h.points.length - 1];
  return (
    <div className="flex flex-col gap-3">
      <PerformanceLineChart
        title="Net worth over time"
        info={`${h.frequency} values from ${h.start} to ${h.end}, in ${h.currency}`}
        actions={picker}
        points={h.points.map((p) => ({
          date: p.on,
          value: p.net_worth.amount,
        }))}
        currency={h.currency}
        summary={`Net worth from ${formatMoney(h.points[0].net_worth.amount, h.currency).text} on ${h.points[0].on} to ${formatMoney(last.net_worth.amount, h.currency).text} on ${last.on}.`}
      />
      {h.incomplete_points > 0 ? (
        <StatusBanner kind="info">
          {h.incomplete_points} of {h.points.length} dates are incomplete: a
          liability&apos;s balance is only known from the date you recorded it,
          or a price or exchange rate was missing.
        </StatusBanner>
      ) : null}
      <DisclosurePanel title="About this history" notices={[h.notice]} />
    </div>
  );
}

function LiabilityDrawer({
  editing,
  currency,
  onClose,
}: {
  editing: Liability | "new" | null;
  currency: string;
  onClose: () => void;
}) {
  return (
    <Drawer
      open={editing !== null}
      title={editing === "new" ? "Add a liability" : "Edit liability"}
      onClose={onClose}
    >
      {editing ? (
        <LiabilityForm
          key={editing === "new" ? "new" : editing.id}
          liability={editing === "new" ? null : editing}
          currency={currency}
          onDone={onClose}
        />
      ) : null}
    </Drawer>
  );
}

function LiabilityForm({
  liability,
  currency,
  onDone,
}: {
  liability: Liability | null;
  currency: string;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const today = new Date().toISOString().slice(0, 10);
  const [values, setValues] = useState<LiabilityValues>(() =>
    liability ? liabilityFromApi(liability) : emptyLiability(currency, today),
  );
  const [problems, setProblems] = useState<
    ReturnType<typeof validateLiability>
  >({});
  const [message, setMessage] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const currencies = useQuery({
    queryKey: ["currencies"],
    queryFn: () => apiGet<S["CurrencyOut"][]>("currencies"),
    staleTime: 3_600_000,
  });
  const set = <K extends keyof LiabilityValues>(
    key: K,
    value: LiabilityValues[K],
  ) => setValues((v) => ({ ...v, [key]: value }));
  const fail = (e: unknown) =>
    setMessage(
      e instanceof ApiError
        ? (e.detail ?? `The server refused this (${e.status}).`)
        : "This could not be sent. Try again.",
    );
  const done = async () => {
    await queryClient.invalidateQueries();
    onDone();
  };
  const save = useMutation({
    mutationFn: () =>
      liability
        ? apiPatch(`liabilities/${liability.id}`, liabilityRequest(values))
        : apiPost("liabilities", liabilityRequest(values)),
    onSuccess: done,
    onError: fail,
  });
  const remove = useMutation({
    mutationFn: () => apiDelete(`liabilities/${liability!.id}`),
    onSuccess: done,
    onError: fail,
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validateLiability(values, today);
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0) save.mutate();
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Name" error={problems.name}>
        {(p) => (
          <input
            {...p}
            maxLength={100}
            value={values.name}
            onChange={(e) => set("name", e.target.value)}
          />
        )}
      </Field>
      <Field label="Type">
        {(p) => (
          <select
            {...p}
            value={values.type}
            onChange={(e) =>
              set("type", e.target.value as LiabilityValues["type"])
            }
          >
            {LIABILITY_TYPES.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field
        label="Balance you owe"
        error={problems.balance}
        hint="Use 0 for a liability you have paid off."
      >
        {(p) => (
          <input
            {...p}
            inputMode="decimal"
            value={values.balance}
            onChange={(e) => set("balance", e.target.value)}
          />
        )}
      </Field>
      <Field label="Currency" error={problems.currency}>
        {(p) => (
          <select
            {...p}
            value={values.currency}
            onChange={(e) => set("currency", e.target.value)}
          >
            {(currencies.data ?? [{ code: values.currency, name: "" }]).map(
              (c) => (
                <option key={c.code} value={c.code}>
                  {c.code}
                </option>
              ),
            )}
          </select>
        )}
      </Field>
      <Field
        label="Balance as of"
        error={problems.asOf}
        hint="The date this balance applied, for example a statement date."
      >
        {(p) => (
          <input
            {...p}
            type="date"
            max={today}
            value={values.asOf}
            onChange={(e) => set("asOf", e.target.value)}
          />
        )}
      </Field>
      <Field label="Interest rate, % a year (optional)" error={problems.rate}>
        {(p) => (
          <input
            {...p}
            inputMode="decimal"
            value={values.rate}
            onChange={(e) => set("rate", e.target.value)}
          />
        )}
      </Field>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending
            ? "Saving…"
            : liability
              ? "Save changes"
              : "Add the liability"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
        {liability ? (
          confirmDelete ? (
            <Button
              variant="primary"
              disabled={remove.isPending}
              onClick={() => remove.mutate()}
            >
              {remove.isPending ? "Deleting…" : "Yes, delete this liability"}
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
              Delete
            </Button>
          )
        ) : null}
      </div>
    </form>
  );
}
