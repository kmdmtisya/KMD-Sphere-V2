"use client";

import { useQueries, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";
import { useStored } from "@/lib/client/local-storage";
import { formatMoney, formatPercent } from "@/lib/format/decimal";

import { Card } from "../cards/cards";
import { AllocationDonutChart } from "../charts/AllocationDonutChart";
import { PerformanceLineChart } from "../charts/PerformanceLineChart";
import { SegmentedControl } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel, SignedAmount } from "../figures/figures";
import { PORTFOLIO_KEY } from "../shell/TopBar";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];
type Portfolio = S["PortfolioOut"];
type Slice = S["SliceOut"];

const RANGES = [
  { value: "1M", label: "1M" },
  { value: "3M", label: "3M" },
  { value: "1Y", label: "1Y" },
  { value: "5Y", label: "5Y" },
  { value: "ALL", label: "All" },
] as const;
type Range = (typeof RANGES)[number]["value"];

/** The start date of a range and the spacing of the series. Dates only: no money is calculated. */
export function rangeParams(
  range: Range,
  today: Date,
): { start?: string; frequency: "daily" | "weekly" | "monthly" } {
  const back = (months: number) => {
    const d = new Date(today);
    d.setUTCMonth(d.getUTCMonth() - months);
    return d.toISOString().slice(0, 10);
  };
  switch (range) {
    case "1M":
      return { start: back(1), frequency: "daily" };
    case "3M":
      return { start: back(3), frequency: "weekly" };
    case "1Y":
      return { start: back(12), frequency: "weekly" };
    case "5Y":
      return { start: back(60), frequency: "monthly" };
    default:
      return { frequency: "monthly" };
  }
}

const RISK_STATUS: Record<S["RiskOut"]["status"], string> = {
  ok: "",
  insufficient_data:
    "There is not enough history in this period to measure risk. Choose a longer range.",
  incomplete_data:
    "Some values in this period are missing prices, so risk figures are not shown.",
  undefined_period: "The period has no start or end that can be measured.",
};
const MONEY_WEIGHTED: Record<S["MoneyWeightedOut"]["status"], string> = {
  ok: "",
  insufficient_flows: "Too few cash flows to work out a money-weighted return.",
  no_sign_change:
    "A money-weighted return needs both money in and money out or a current value.",
  no_rate_in_range: "No single rate explains these cash flows.",
};

function Figure({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | null;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5" title={hint}>
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {label}
      </dt>
      <dd className="text-[length:var(--ws-font-size-title)] font-semibold tabular-nums">
        {value ?? "Not available"}
      </dd>
    </div>
  );
}

/** Financial analytics (P14-T09): every figure and series is the backend's; the page only shows them. */
export function Analytics() {
  const [stored] = useStored(PORTFOLIO_KEY);
  const [choice, setChoice] = useState<string | null>(null);
  const [range, setRange] = useState<Range>("1Y");
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () => apiGet<Portfolio[]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  if (portfolios.isPending) return <LoadingState label="Loading portfolios" />;
  if (portfolios.isError)
    return (
      <ErrorState
        message="Portfolios could not be loaded."
        onRetry={() => void portfolios.refetch()}
      />
    );
  const list = portfolios.data;
  if (!list.length)
    return (
      <EmptyState title="No portfolios to analyse">
        Create a portfolio and add transactions first.
      </EmptyState>
    );
  const selectedId =
    [choice, stored].find((id) => id && list.some((p) => p.id === id)) ??
    list[0].id;
  const portfolio = list.find((p) => p.id === selectedId) ?? list[0];
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Analytics
          </h1>
          <p className="text-fg-muted">
            Performance, allocation and risk, calculated by the backend from
            your ledger.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-48">
            <Field label="Portfolio">
              {(p) => (
                <select
                  {...p}
                  value={portfolio.id}
                  onChange={(e) => setChoice(e.target.value)}
                >
                  {list.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <SegmentedControl
            label="Period"
            options={RANGES}
            value={range}
            onChange={setRange}
          />
        </div>
      </header>
      <Performance
        key={`p-${portfolio.id}`}
        portfolio={portfolio}
        range={range}
      />
      <AllocationSection key={`a-${portfolio.id}`} portfolio={portfolio} />
      {list.length > 1 ? (
        <Comparison portfolios={list} current={portfolio.id} />
      ) : null}
    </div>
  );
}

function Performance({
  portfolio,
  range,
}: {
  portfolio: Portfolio;
  range: Range;
}) {
  const perf = useQuery({
    queryKey: ["performance", portfolio.id],
    queryFn: () =>
      apiGet<S["PerformanceOut"]>(`portfolios/${portfolio.id}/performance`),
    staleTime: 60_000,
  });
  const params = rangeParams(range, new Date());
  const risk = useQuery({
    queryKey: ["risk", portfolio.id, range],
    queryFn: () =>
      apiGet<S["RiskOut"]>(
        `portfolios/${portfolio.id}/risk?frequency=${params.frequency}${params.start ? `&start=${params.start}` : ""}`,
      ),
    staleTime: 60_000,
  });
  if (perf.isPending)
    return (
      <Card title="Performance">
        <LoadingState label="Loading performance" />
      </Card>
    );
  if (perf.isError)
    return (
      <Card title="Performance">
        <ErrorState
          message="Performance could not be loaded."
          onRetry={() => void perf.refetch()}
        />
      </Card>
    );
  const p = perf.data;
  const r = risk.data;
  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Performance"
        info="Since your first entry; the period selector below applies to the value chart and risk"
        actions={<DataAsOfLabel asOf={p.as_of} />}
      >
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Figure
            label="Total value"
            value={formatMoney(p.total_value.amount, p.currency).text}
          />
          <div className="flex flex-col gap-0.5">
            <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
              Profit or loss
            </dt>
            <dd className="text-[length:var(--ws-font-size-title)]">
              <SignedAmount
                value={p.profit_loss.amount}
                currency={p.currency}
              />
            </dd>
          </div>
          <Figure
            label="Return on money invested"
            value={p.return_percent ? formatPercent(p.return_percent) : null}
            hint="Profit or loss as a share of the net amount invested"
          />
          <Figure
            label="Money-weighted return, a year (XIRR)"
            value={
              p.money_weighted.annual_return_percent
                ? formatPercent(p.money_weighted.annual_return_percent)
                : null
            }
            hint="The rate that explains your cash flows, which counts when you paid in"
          />
          <Figure
            label="Net invested"
            value={formatMoney(p.net_invested.amount, p.currency).text}
          />
          <Figure
            label="Income received"
            value={formatMoney(p.income.amount, p.currency).text}
          />
          <Figure
            label="Realised profit or loss"
            value={formatMoney(p.realized_pl.amount, p.currency).text}
          />
          <Figure
            label="Unrealised profit or loss"
            value={formatMoney(p.unrealized_pl.amount, p.currency).text}
          />
        </dl>
        {MONEY_WEIGHTED[p.money_weighted.status] ? (
          <p className="mt-3 text-fg-muted">
            {MONEY_WEIGHTED[p.money_weighted.status]}
          </p>
        ) : null}
        {!p.complete ? (
          <div className="mt-3">
            <StatusBanner kind="stale">
              Some assets have no price yet, so these figures are incomplete.
            </StatusBanner>
          </div>
        ) : null}
        {p.assumed_deposit_count > 0 ? (
          <div className="mt-3">
            <StatusBanner kind="info">
              {p.assumed_deposit_count} holding(s) have no recorded purchase, so
              a deposit of{" "}
              {formatMoney(p.assumed_deposits.amount, p.currency).text} on the
              first date is assumed.
            </StatusBanner>
          </div>
        ) : null}
        <div className="mt-3">
          <DisclosurePanel title="About these figures" notices={[p.notice]} />
        </div>
      </Card>

      {risk.isPending ? (
        <Card title="Value over time">
          <LoadingState label="Loading the value series" />
        </Card>
      ) : null}
      {risk.isError ? (
        <Card title="Value over time">
          <ErrorState
            message="The value series could not be loaded."
            onRetry={() => void risk.refetch()}
          />
        </Card>
      ) : null}
      {r ? (
        <>
          {r.points.length > 1 ? (
            <PerformanceLineChart
              title="Value over time"
              info={`${r.frequency} values from ${r.start} to ${r.end}, in ${r.currency}`}
              points={r.points.map((pt) => ({
                date: pt.on,
                value: pt.value.amount,
              }))}
              currency={r.currency}
              summary={`Portfolio value from ${formatMoney(r.points[0].value.amount, r.currency).text} on ${r.points[0].on} to ${formatMoney(r.points[r.points.length - 1].value.amount, r.currency).text} on ${r.points[r.points.length - 1].on}.`}
            />
          ) : (
            <Card title="Value over time">
              <EmptyState title="Not enough history">
                Add transactions or choose a longer period to see the value over
                time.
              </EmptyState>
            </Card>
          )}
          <Card title="Risk" info="Measured on this period's value series">
            {RISK_STATUS[r.status] ? (
              <p className="mb-3 text-fg-muted">{RISK_STATUS[r.status]}</p>
            ) : null}
            <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <Figure
                label="Time-weighted return"
                value={
                  r.time_weighted_return_percent
                    ? formatPercent(r.time_weighted_return_percent)
                    : null
                }
                hint="Removes the effect of when money was paid in or out"
              />
              <Figure
                label="Time-weighted, a year"
                value={
                  r.time_weighted_annualized_percent
                    ? formatPercent(r.time_weighted_annualized_percent)
                    : null
                }
                hint="The compound annual growth rate of the time-weighted return"
              />
              <Figure
                label="Volatility, a year"
                value={
                  r.volatility_percent
                    ? formatPercent(r.volatility_percent)
                    : null
                }
                hint="How much returns varied, scaled to a year"
              />
              <Figure
                label="Largest fall"
                value={
                  r.max_drawdown
                    ? `${formatPercent(r.max_drawdown.depth_percent)} (${r.max_drawdown.peak} to ${r.max_drawdown.trough}${r.max_drawdown.recovered ? `, recovered ${r.max_drawdown.recovered}` : ", not yet recovered"})`
                    : null
                }
                hint="The deepest drop from a peak to a later low"
              />
            </dl>
            {r.incomplete_points > 0 ? (
              <p className="mt-3 text-fg-muted">
                {r.incomplete_points} point(s) in the series are missing a price
                and are excluded.
              </p>
            ) : null}
            <div className="mt-3">
              <DisclosurePanel
                title="About risk figures"
                notices={[r.notice]}
              />
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

type Dimension = "asset_class" | "country" | "currency_exposure" | "sector";
const DIMENSIONS: { id: Dimension; label: string }[] = [
  { id: "asset_class", label: "Asset class" },
  { id: "currency_exposure", label: "Currency" },
  { id: "country", label: "Country" },
  { id: "sector", label: "Sector" },
];

function AllocationSection({ portfolio }: { portfolio: Portfolio }) {
  const [dimension, setDimension] = useState<Dimension>("asset_class");
  const [slice, setSlice] = useState<string | null>(null);
  const allocation = useQuery({
    queryKey: ["allocation", portfolio.id],
    queryFn: () =>
      apiGet<S["AllocationOut"]>(`portfolios/${portfolio.id}/allocation`),
    staleTime: 60_000,
  });
  const holdings = useQuery({
    queryKey: ["holdings", portfolio.id, "open"],
    queryFn: () =>
      apiGet<S["HoldingOut"][]>(
        `portfolios/${portfolio.id}/holdings?include_closed=false`,
      ),
    staleTime: 60_000,
  });
  if (allocation.isPending)
    return (
      <Card title="Allocation">
        <LoadingState label="Loading allocation" />
      </Card>
    );
  if (allocation.isError)
    return (
      <Card title="Allocation">
        <ErrorState
          message="Allocation could not be loaded."
          onRetry={() => void allocation.refetch()}
        />
      </Card>
    );
  const a = allocation.data;
  const slices: Slice[] = a[dimension].slices;
  const labelOf = (s: Slice) => s.key ?? "Unclassified";
  const items = slices.map((s) => ({
    label: labelOf(s),
    percent: s.weight_percent ?? "0",
    amount: s.value.amount,
  }));
  const chosen = slices.find((s) => labelOf(s) === slice);
  // Drill-down: the holdings behind a slice of the asset-class or currency view.
  const behind =
    chosen &&
    holdings.data &&
    (dimension === "asset_class" || dimension === "currency_exposure")
      ? holdings.data.filter(
          (h) =>
            (dimension === "asset_class"
              ? h.asset.asset_class
              : h.asset.currency) === chosen.key,
        )
      : [];
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[length:var(--ws-font-size-title)] font-semibold">
          Allocation
        </h2>
        <SegmentedControl
          label="View by"
          options={DIMENSIONS.map((d) => ({ value: d.id, label: d.label }))}
          value={dimension}
          onChange={(v) => {
            setDimension(v);
            setSlice(null);
          }}
        />
      </div>
      {!a.complete ? (
        <StatusBanner kind="stale">
          {a.unpriced_assets} asset(s) have no price yet and are left out of
          these shares.
        </StatusBanner>
      ) : null}
      {items.length ? (
        <AllocationDonutChart
          title={`By ${DIMENSIONS.find((d) => d.id === dimension)!.label.toLowerCase()}`}
          info={
            a[dimension].hhi
              ? `Concentration index (HHI) ${a[dimension].hhi}: higher means more concentrated`
              : undefined
          }
          currency={a.currency}
          items={items}
          summary={`Allocation by ${dimension.replace("_", " ")}: ${items.map((i) => `${i.label} ${formatPercent(i.percent)}`).join(", ")}.`}
        />
      ) : (
        <Card title="Allocation">
          <EmptyState title="Nothing to show">
            This view has no data for the portfolio yet.
          </EmptyState>
        </Card>
      )}
      {dimension === "asset_class" || dimension === "currency_exposure" ? (
        <Card
          title="Look inside a slice"
          info="Pick a slice to list the holdings behind it"
        >
          <div
            role="group"
            aria-label="Slices"
            className="mb-3 flex flex-wrap gap-2"
          >
            {slices.map((s) => (
              <button
                key={labelOf(s)}
                type="button"
                aria-pressed={slice === labelOf(s)}
                onClick={() =>
                  setSlice(slice === labelOf(s) ? null : labelOf(s))
                }
                className="min-h-9 rounded-[var(--ws-radius-pill)] border border-line px-3 font-semibold aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-on-primary"
              >
                {labelOf(s)}
              </button>
            ))}
          </div>
          {chosen ? (
            behind.length ? (
              <DataGrid
                caption={`Holdings in ${labelOf(chosen)}`}
                rowKey="id"
                rows={behind.map((h) => ({
                  id: h.asset.id,
                  asset: h.asset.name,
                  quantity: h.quantity,
                  value: h.value?.amount ?? "",
                  currency: a.currency,
                }))}
                columns={[
                  { key: "asset", header: "Asset" },
                  { key: "quantity", header: "Quantity", align: "end" },
                  {
                    key: "value",
                    header: "Value",
                    kind: "money",
                    currencyKey: "currency",
                  },
                ]}
              />
            ) : (
              <p className="text-fg-muted">No open holdings in this slice.</p>
            )
          ) : (
            <p className="text-fg-muted">Choose a slice above.</p>
          )}
        </Card>
      ) : null}
      <Card
        title="Concentration"
        info="How much of the portfolio sits in its largest positions"
      >
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Figure label="Positions" value={String(a.concentration.positions)} />
          <Figure
            label="Largest position"
            value={a.concentration.largest ?? null}
          />
          <Figure
            label="Top position's share"
            value={
              a.concentration.top_1_percent
                ? formatPercent(a.concentration.top_1_percent)
                : null
            }
          />
          <Figure
            label="Top 3 / top 5 share"
            value={
              a.concentration.top_3_percent && a.concentration.top_5_percent
                ? `${formatPercent(a.concentration.top_3_percent)} / ${formatPercent(a.concentration.top_5_percent)}`
                : null
            }
          />
        </dl>
      </Card>
    </div>
  );
}

/** Portfolios side by side (P14-T09.4): the same backend figures for each. */
function Comparison({
  portfolios,
  current,
}: {
  portfolios: Portfolio[];
  current: string;
}) {
  const results = useQueries({
    queries: portfolios
      .slice(0, 8)
      .map((p) => ({
        queryKey: ["performance", p.id],
        queryFn: () =>
          apiGet<S["PerformanceOut"]>(`portfolios/${p.id}/performance`),
        staleTime: 60_000,
      })),
  });
  if (results.some((r) => r.isPending))
    return (
      <Card title="Compare portfolios">
        <LoadingState label="Loading the comparison" />
      </Card>
    );
  const rows = portfolios.slice(0, 8).flatMap((p, i) => {
    const d = results[i].data;
    return d
      ? [
          {
            id: p.id,
            name: p.id === current ? `${p.name} (shown above)` : p.name,
            value: d.total_value.amount,
            profit: d.profit_loss.amount,
            ret: d.return_percent ? formatPercent(d.return_percent) : "n/a",
            xirr: d.money_weighted.annual_return_percent
              ? formatPercent(d.money_weighted.annual_return_percent)
              : "n/a",
            currency: d.currency,
          },
        ]
      : [];
  });
  return (
    <Card
      title="Compare portfolios"
      info="Each in its own currency; figures are not added together"
    >
      <DataGrid
        caption="Portfolio comparison"
        rowKey="id"
        rows={rows}
        columns={[
          { key: "name", header: "Portfolio" },
          {
            key: "value",
            header: "Value",
            kind: "money",
            currencyKey: "currency",
          },
          {
            key: "profit",
            header: "Profit or loss",
            kind: "money",
            currencyKey: "currency",
            render: (r) => (
              <SignedAmount value={r.profit} currency={r.currency} />
            ),
          },
          { key: "ret", header: "Return", align: "end" },
          { key: "xirr", header: "XIRR, a year", align: "end" },
        ]}
      />
    </Card>
  );
}
