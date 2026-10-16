"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import type { components } from "@/lib/api";
import { ApiError, apiGet, apiPost } from "@/lib/client/api";
import { useStored } from "@/lib/client/local-storage";

import { KpiCard } from "../cards/cards";
import { Button } from "../controls/controls";
import { Drawer } from "../controls/forms";
import { DataGrid, type GridColumn } from "../data/DataGrid";
import { CurrencyAmount, SignedAmount, StaleChip } from "../figures/figures";
import { EmptyState, ErrorState, LoadingState, StatusBanner } from "../states/states";
import { Versioned } from "../controls/Versioned";
import { PortfolioForm } from "./PortfolioList";
import { TransactionDrawer } from "./TransactionDrawer";
import { TransactionsTable } from "./TransactionsTable";
import { ValuationsPanel } from "./ValuationsPanel";

type Portfolio = components["schemas"]["PortfolioOut"];
type Holding = components["schemas"]["HoldingOut"];
type Tab = "holdings" | "transactions" | "valuations";
const TABS: { id: Tab; label: string }[] = [
  { id: "holdings", label: "Holdings" },
  { id: "transactions", label: "Transactions" },
  { id: "valuations", label: "Valuations" },
];

/** One portfolio (P14-T08.1, T08.2): summary figures, then tabs for holdings, ledger and valuations. */
export function PortfolioDetail({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("holdings");
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState(false);
  const portfolio = useQuery({ queryKey: ["portfolio", id], queryFn: () => apiGet<Portfolio>(`portfolios/${id}`), staleTime: 30_000 });
  const summary = useQuery({ queryKey: ["portfolio-summary", id], queryFn: () => apiGet<components["schemas"]["SummaryOut"]>(`portfolios/${id}/summary`), staleTime: 30_000 });
  const archive = useMutation({
    mutationFn: () => apiPost<Portfolio>(`portfolios/${id}/archive`, {}),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  if (portfolio.isPending) return <LoadingState label="Loading the portfolio" />;
  if (portfolio.isError) {
    const missing = portfolio.error instanceof ApiError && portfolio.error.status === 404;
    return missing ? (
      <EmptyState title="Portfolio not found" action={<Link href="/portfolio" className="font-semibold text-primary underline">Back to portfolios</Link>}>
        It may not exist, or it is not yours.
      </EmptyState>
    ) : (
      <ErrorState message="The portfolio could not be loaded." onRetry={() => void portfolio.refetch()} />
    );
  }
  const p = portfolio.data;
  const s = summary.data;
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <nav aria-label="Breadcrumb" className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        <Link href="/portfolio" className="underline">Portfolios</Link> / {p.name}
      </nav>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">{p.name}</h1>
          <p className="text-fg-muted">{p.portfolio_type} · {p.base_currency}{p.description ? ` · ${p.description}` : ""}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="arrowUp" disabled={Boolean(p.archived_at)} onClick={() => setAdding(true)}>Add a transaction</Button>
          <Button onClick={() => setEditing(true)}>Edit</Button>
          <Button disabled={Boolean(p.archived_at) || archive.isPending} onClick={() => archive.mutate()}>Archive</Button>
        </div>
      </header>
      {p.archived_at ? <StatusBanner kind="info">This portfolio is archived: it is read-only.</StatusBanner> : null}
      {archive.isError ? <StatusBanner kind="warning">The portfolio could not be archived.</StatusBanner> : null}

      {summary.isPending ? <LoadingState label="Loading figures" lines={2} /> : null}
      {summary.isError ? <ErrorState message="The figures could not be loaded." onRetry={() => void summary.refetch()} /> : null}
      {s ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <KpiCard label="Total value" info="Holdings at their latest value plus cash, in the portfolio's currency" value={s.total_value.amount} currency={s.currency} footer={s.unpriced_assets.length ? <StaleChip /> : undefined} />
          <KpiCard label="Cash" value={s.cash.amount} currency={s.currency} />
          <KpiCard label="Cost basis" value={s.cost_basis.amount} currency={s.currency} />
          <div className="rounded-[var(--ws-radius-card)] border border-divider bg-surface p-5">
            <h2 className="mb-2 text-[length:var(--ws-font-size-label)] font-semibold text-fg-muted">Profit or loss</h2>
            <div className="flex flex-col gap-1 text-[length:var(--ws-font-size-title)]">
              <span>Unrealised <SignedAmount value={s.unrealized_pl.amount} currency={s.currency} /></span>
              <span>Realised <SignedAmount value={s.realized_pl.amount} currency={s.currency} /></span>
            </div>
          </div>
        </div>
      ) : null}
      {s?.unpriced_assets.length ? <StatusBanner kind="stale">{s.unpriced_assets.length} asset(s) have no price or valuation yet, so they are not in the total. Add a valuation for them.</StatusBanner> : null}

      <div role="tablist" aria-label="Portfolio sections" className="flex gap-1 border-b border-divider">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            type="button"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => setTab(t.id)}
            className={`-mb-px min-h-9 border-b-2 px-4 font-semibold ${tab === t.id ? "border-primary text-fg" : "border-transparent text-fg-muted"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
        {tab === "holdings" ? <Holdings portfolio={p} /> : null}
        {tab === "transactions" ? <TransactionsTable portfolio={p} /> : null}
        {tab === "valuations" ? <ValuationsPanel portfolio={p} /> : null}
      </div>

      <TransactionDrawer portfolio={p} open={adding} onClose={() => setAdding(false)} />
      <Drawer open={editing} title="Edit the portfolio" onClose={() => setEditing(false)}>
        {editing ? (
          <Versioned<components["schemas"]["PortfolioOut"]> path={`portfolios/${p.id}`}>
            {(record, etag, reload) => <PortfolioForm existing={record} etag={etag} onStale={reload} onDone={() => setEditing(false)} />}
          </Versioned>
        ) : null}
      </Drawer>
    </div>
  );
}

const HOLDING_COLUMNS: { key: string; label: string; always?: boolean }[] = [
  { key: "asset", label: "Asset", always: true },
  { key: "quantity", label: "Quantity" },
  { key: "average", label: "Average cost" },
  { key: "cost", label: "Cost basis" },
  { key: "value", label: "Value" },
  { key: "realised", label: "Realised P/L" },
  { key: "income", label: "Income" },
];

/**
 * Holdings (P14-T08.2). Which columns show is a saved table view: kept per browser, never in the
 * account (DEC-35). Figures are the API's; nothing is calculated here.
 */
function Holdings({ portfolio }: { portfolio: Portfolio }) {
  const [saved, save] = useStored("ws.view.holdings");
  const hidden = new Set((saved ?? "").split(",").filter(Boolean));
  const [closed, setClosed] = useState(false);
  const holdings = useQuery({
    queryKey: ["holdings", portfolio.id, closed ? "all" : "open"],
    queryFn: () => apiGet<Holding[]>(`portfolios/${portfolio.id}/holdings?include_closed=${closed}`),
    staleTime: 30_000,
  });
  if (holdings.isPending) return <LoadingState label="Loading holdings" />;
  if (holdings.isError) return <ErrorState message="Holdings could not be loaded." onRetry={() => void holdings.refetch()} />;
  const money = (m: components["schemas"]["Money"] | null | undefined) => (m ? m.amount : "");
  const ccy = portfolio.base_currency;
  const rows = holdings.data.map((h) => ({
    id: h.asset.id,
    asset: h.asset.name,
    symbol: h.asset.symbol ?? "",
    quantity: h.quantity,
    average: money(h.average_cost),
    cost: h.cost_basis.amount,
    value: money(h.value),
    stale: h.value_stale ? "yes" : "",
    realised: h.realized_pl.amount,
    income: h.income.amount,
    currency: ccy,
  }));
  const all: (GridColumn<(typeof rows)[number]> & { id: string })[] = [
    { id: "asset", key: "asset", header: "Asset", render: (r) => <span className="font-medium">{r.asset}{r.symbol ? <span className="ms-1 text-fg-muted">{r.symbol}</span> : null}</span> },
    { id: "quantity", key: "quantity", header: "Quantity", align: "end" },
    { id: "average", key: "average", header: "Average cost", kind: "money", currencyKey: "currency" },
    { id: "cost", key: "cost", header: "Cost basis", kind: "money", currencyKey: "currency" },
    { id: "value", key: "value", header: "Value", kind: "money", currencyKey: "currency", render: (r) => (r.value ? <span className="inline-flex items-center gap-2"><CurrencyAmount value={r.value} currency={ccy} />{r.stale ? <StaleChip /> : null}</span> : <span className="text-fg-muted">No value yet</span>) },
    { id: "realised", key: "realised", header: "Realised P/L", kind: "money", currencyKey: "currency", render: (r) => <SignedAmount value={r.realised} currency={ccy} /> },
    { id: "income", key: "income", header: "Income", kind: "money", currencyKey: "currency" },
  ];
  const shown = all.filter((c) => !hidden.has(c.id));
  const toggle = (key: string) => {
    const next = new Set(hidden);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    save([...next].join(","));
  };
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-4">
        <fieldset className="flex flex-wrap items-center gap-3">
          <legend className="sr-only">Columns shown</legend>
          <span className="font-semibold text-fg-muted">Columns:</span>
          {HOLDING_COLUMNS.filter((c) => !c.always).map((c) => (
            <label key={c.key} className="inline-flex items-center gap-1">
              <input type="checkbox" checked={!hidden.has(c.key)} onChange={() => toggle(c.key)} />
              {c.label}
            </label>
          ))}
        </fieldset>
        <label className="inline-flex items-center gap-1">
          <input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />
          Include closed positions
        </label>
      </div>
      {rows.length ? <DataGrid caption={`Holdings of ${portfolio.name}`} rowKey="id" rows={rows} columns={shown} /> : <EmptyState title="No holdings">Buy an asset or add a valuation to see holdings here.</EmptyState>}
    </div>
  );
}
