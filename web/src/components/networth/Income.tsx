"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";
import { formatMoney, formatPercent } from "@/lib/format/decimal";

import { Card, KpiCard } from "../cards/cards";
import { PerformanceLineChart } from "../charts/PerformanceLineChart";
import { Field } from "../controls/forms";
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

const TYPE_LABEL: Record<string, string> = {
  DIVIDEND: "Dividends",
  INTEREST: "Interest",
  COUPON: "Coupons",
  RENT: "Rent",
  DISTRIBUTION: "Distributions",
};

/**
 * Passive income (P14-T11.2): what your portfolios paid out (dividends, interest, rent, coupons),
 * as the backend totals it. Gross, fees, taxes and net are shown separately; a yield is the
 * server's, never recomputed here.
 */
export function Income() {
  const [choice, setChoice] = useState<string | null>(null);
  const summary = useQuery({
    queryKey: ["income-summary"],
    queryFn: () => apiGet<S["IncomeSummaryOut"]>("income/summary"),
    staleTime: 60_000,
  });
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });

  if (summary.isPending || portfolios.isPending)
    return <LoadingState label="Loading income" />;
  if (summary.isError || portfolios.isError) {
    return (
      <ErrorState
        message="Income could not be loaded."
        onRetry={() =>
          void Promise.all([summary.refetch(), portfolios.refetch()])
        }
      />
    );
  }
  const s = summary.data;
  const list = portfolios.data;
  const names = new Map(list.map((p) => [p.id, p.name]));
  const selected = list.find((p) => p.id === choice) ?? list[0];

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Income
          </h1>
          <p className="text-fg-muted">
            Dividends, interest, rent and coupons your portfolios paid, in{" "}
            {s.currency}.
          </p>
        </div>
        <DataAsOfLabel asOf={s.as_of} />
      </header>
      {!s.complete ? (
        <StatusBanner kind="stale">
          Income in {s.unconverted_currencies.join(", ") || "some currencies"}{" "}
          could not be converted and is left out of these totals.
        </StatusBanner>
      ) : null}
      <div className="grid gap-4 md:grid-cols-3">
        <KpiCard
          label="Per month"
          value={s.monthly.amount}
          currency={s.currency}
          info="The last 12 months, averaged, after fees and taxes"
        />
        <KpiCard
          label="Per year (net)"
          value={s.yearly.amount}
          currency={s.currency}
          info="The last 12 months, after fees and taxes"
        />
        <KpiCard
          label="Per year (gross)"
          value={s.yearly_gross.amount}
          currency={s.currency}
          info="The last 12 months, before fees and taxes"
        />
      </div>
      {s.portfolios.length ? (
        <Card
          title="By portfolio"
          info="Net income over the last 12 months, each as a share of that portfolio's value"
        >
          <DataGrid
            caption="Income by portfolio"
            rowKey="id"
            rows={s.portfolios.map((p) => ({
              id: p.portfolio_id,
              name: names.get(p.portfolio_id) ?? "Portfolio",
              yearly: p.yearly.amount,
              value: p.value?.amount ?? "",
              currency: s.currency,
            }))}
            columns={[
              { key: "name", header: "Portfolio" },
              {
                key: "yearly",
                header: "Net a year",
                kind: "money",
                currencyKey: "currency",
              },
              {
                key: "value",
                header: "Portfolio value",
                kind: "money",
                currencyKey: "currency",
              },
            ]}
          />
        </Card>
      ) : null}
      {list.length === 0 ? (
        <EmptyState title="No portfolios yet">
          Create a portfolio and record dividends, interest or rent to see
          income here.
        </EmptyState>
      ) : (
        <>
          <div className="max-w-xs">
            <Field label="Portfolio">
              {(p) => (
                <select
                  {...p}
                  value={selected.id}
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
          <PortfolioIncome key={selected.id} portfolio={selected} />
        </>
      )}
    </div>
  );
}

function PortfolioIncome({ portfolio }: { portfolio: S["PortfolioOut"] }) {
  const income = useQuery({
    queryKey: ["portfolio-income", portfolio.id],
    queryFn: () =>
      apiGet<S["PortfolioIncomeOut"]>(`portfolios/${portfolio.id}/income`),
    staleTime: 60_000,
  });
  const holdings = useQuery({
    queryKey: ["holdings", portfolio.id, "all"],
    queryFn: () =>
      apiGet<S["HoldingOut"][]>(
        `portfolios/${portfolio.id}/holdings?include_closed=true`,
      ),
    staleTime: 60_000,
  });
  if (income.isPending)
    return <LoadingState label="Loading this portfolio's income" />;
  if (income.isError)
    return (
      <ErrorState
        message="This portfolio's income could not be loaded."
        onRetry={() => void income.refetch()}
      />
    );
  const i = income.data;
  const t = i.trailing_12m;
  if (t.payments === 0 && i.months.length === 0) {
    return (
      <EmptyState title="No income recorded">
        Dividends, interest, rent and coupons you record in this portfolio
        appear here.
      </EmptyState>
    );
  }
  const names = new Map(
    (holdings.data ?? []).map((h) => [h.asset.id, h.asset.name]),
  );
  return (
    <div className="flex flex-col gap-4">
      <Card
        title="The last 12 months"
        info="Totals as recorded in the ledger"
        actions={<DataAsOfLabel asOf={i.as_of} />}
      >
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <Stat
            label="Gross"
            value={formatMoney(t.gross.amount, i.currency).text}
          />
          <Stat
            label="Fees"
            value={formatMoney(t.fees.amount, i.currency).text}
          />
          <Stat
            label="Taxes"
            value={formatMoney(t.taxes.amount, i.currency).text}
          />
          <Stat
            label="Net"
            value={formatMoney(t.net.amount, i.currency).text}
          />
          <Stat
            label="Yield on portfolio value"
            value={
              i.portfolio_yield_percent
                ? formatPercent(i.portfolio_yield_percent)
                : "Not available"
            }
          />
        </dl>
        <p className="mt-3 text-fg-muted">{t.payments} payment(s).</p>
        {!i.complete ? (
          <div className="mt-3">
            <StatusBanner kind="stale">
              Some income could not be converted or the portfolio has unpriced
              assets, so the figures are incomplete.
            </StatusBanner>
          </div>
        ) : null}
      </Card>
      {i.months.length > 1 ? (
        <PerformanceLineChart
          title="Net income by month"
          currency={i.currency}
          points={i.months.map((m) => ({
            date: `${m.period}-01`,
            value: m.totals.net.amount,
          }))}
          summary={`Net income for ${i.months.length} months, the latest ${formatMoney(i.months[i.months.length - 1].totals.net.amount, i.currency).text} in ${i.months[i.months.length - 1].period}.`}
        />
      ) : null}
      {i.by_type.length ? (
        <Card title="By type">
          <DataGrid
            caption="Income by type"
            rowKey="type"
            rows={i.by_type.map((x) => ({
              type: x.income_type,
              label: TYPE_LABEL[x.income_type] ?? x.income_type,
              last12: x.trailing_12m.net.amount,
              all: x.all_time.net.amount,
              currency: i.currency,
            }))}
            columns={[
              { key: "label", header: "Type" },
              {
                key: "last12",
                header: "Net, last 12 months",
                kind: "money",
                currencyKey: "currency",
              },
              {
                key: "all",
                header: "Net, all time",
                kind: "money",
                currencyKey: "currency",
              },
            ]}
          />
        </Card>
      ) : null}
      {i.by_asset.length ? (
        <Card
          title="By asset"
          info="Yield on cost compares income with what you paid; current yield with today's value"
        >
          <DataGrid
            caption="Income by asset"
            rowKey="id"
            rows={i.by_asset.map((x, n) => ({
              id: x.asset_id ?? `cash-${n}`,
              asset: x.asset_id ? (names.get(x.asset_id) ?? "Asset") : "Cash",
              last12: x.trailing_12m.net.amount,
              currentYield: x.current_yield_percent
                ? formatPercent(x.current_yield_percent)
                : "n/a",
              costYield: x.yield_on_cost_percent
                ? formatPercent(x.yield_on_cost_percent)
                : "n/a",
              currency: i.currency,
            }))}
            columns={[
              { key: "asset", header: "Asset" },
              {
                key: "last12",
                header: "Net, last 12 months",
                kind: "money",
                currencyKey: "currency",
              },
              { key: "currentYield", header: "Current yield", align: "end" },
              { key: "costYield", header: "Yield on cost", align: "end" },
            ]}
          />
        </Card>
      ) : null}
      <DisclosurePanel
        title="About income figures"
        notices={[
          "Income is what was recorded in your ledger. Past income does not predict future income, and no payment is guaranteed.",
        ]}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {label}
      </dt>
      <dd className="text-[length:var(--ws-font-size-title)] font-semibold tabular-nums">
        {value}
      </dd>
    </div>
  );
}
