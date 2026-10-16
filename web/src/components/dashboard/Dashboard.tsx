"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPatch, apiPost } from "@/lib/client/api";
import { moveSection, normaliseLayout, SECTION_LABELS, toggleSection, visibleSections, type Layout, type Section } from "@/lib/dashboard/layout";
import { formatMoney, formatPercent } from "@/lib/format/decimal";

import { Card, KpiCard } from "../cards/cards";
import { AllocationDonutChart } from "../charts/AllocationDonutChart";
import { Button, IconButton } from "../controls/controls";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel, SignedAmount, StaleChip } from "../figures/figures";
import { DisclosurePanel, EmptyState, ErrorState, LoadingState, StatusBanner } from "../states/states";

type S = components["schemas"];
const STALE_MS = 60_000;

/** Whether the browser is online; the dashboard says so instead of silently showing old figures. */
function useOnline(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      window.addEventListener("online", onChange);
      window.addEventListener("offline", onChange);
      return () => {
        window.removeEventListener("online", onChange);
        window.removeEventListener("offline", onChange);
      };
    },
    () => navigator.onLine,
    () => true,
  );
}

function Section({ title, query, children }: { title: string; query: { isPending: boolean; isError: boolean; refetch: () => unknown }; children: React.ReactNode }) {
  if (query.isPending) return <Card title={title}><LoadingState label={`Loading ${title}`} /></Card>;
  if (query.isError) return <Card title={title}><ErrorState message={`${title} could not be loaded.`} onRetry={() => void query.refetch()} /></Card>;
  return <>{children}</>;
}

function WealthSummary() {
  const dashboard = useQuery({ queryKey: ["dashboard"], queryFn: () => apiGet<S["DashboardOut"]>("dashboard"), staleTime: STALE_MS });
  const netWorth = useQuery({ queryKey: ["net-worth"], queryFn: () => apiGet<S["NetWorthOut"]>("net-worth"), staleTime: STALE_MS });
  const query = dashboard.isError ? dashboard : netWorth.isError ? netWorth : dashboard.isPending ? dashboard : netWorth;
  const d = dashboard.data;
  const n = netWorth.data;
  return (
    <Section title="Wealth summary" query={query}>
      {d && n ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <DataAsOfLabel asOf={d.as_of} />
            {!d.complete || !n.freshness.complete ? <StaleChip since={n.freshness.data_as_of} /> : null}
          </div>
          {!d.complete ? <StatusBanner kind="stale">Some figures are incomplete or out of date: unpriced assets or old exchange rates are not included at their current value.</StatusBanner> : null}
          <div className="grid gap-4 md:grid-cols-3">
            <KpiCard label="Net worth" info="Assets minus liabilities, in your reporting currency" value={d.net_worth.net_worth.amount} currency={d.currency} />
            <KpiCard label="Assets" value={d.net_worth.assets.amount} currency={d.currency} />
            <KpiCard label="Liabilities" value={d.net_worth.liabilities.amount} currency={d.currency} />
          </div>
          {n.assets_by_class.length ? (
            <AllocationDonutChart
              title="Assets by class"
              info="Share of your assets in each asset class"
              currency={d.currency}
              items={n.assets_by_class.map((c) => ({ label: c.asset_class, percent: c.share_percent ?? "0", amount: c.value.amount }))}
              summary={`Assets by class: ${n.assets_by_class.map((c) => `${c.asset_class} ${c.share_percent ? formatPercent(c.share_percent) : "share unknown"}`).join(", ")}.`}
            />
          ) : (
            <Card title="Assets by class">
              <EmptyState title="No assets yet">Add a portfolio and your first investment to see how your wealth is spread.</EmptyState>
            </Card>
          )}
        </div>
      ) : null}
    </Section>
  );
}

function Metrics() {
  const summary = useQuery({ queryKey: ["portfolio-summary"], queryFn: () => apiGet<S["SummaryOut"]>("portfolios/consolidated/summary"), staleTime: STALE_MS });
  const income = useQuery({ queryKey: ["income-summary"], queryFn: () => apiGet<S["IncomeSummaryOut"]>("income/summary"), staleTime: STALE_MS });
  const goals = useQuery({ queryKey: ["goals-summary"], queryFn: () => apiGet<S["GoalsSummaryOut"]>("goals/summary"), staleTime: STALE_MS });
  const query = [summary, income, goals].find((q) => q.isError) ?? [summary, income, goals].find((q) => q.isPending) ?? summary;
  const sm = summary.data;
  const inc = income.data;
  const g = goals.data;
  return (
    <div className="flex flex-col gap-4">
      <Section title="Key figures" query={query}>
        {sm && inc && g ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Portfolio value" info="Holdings and cash across all your portfolios" value={sm.total_value.amount} currency={sm.currency} footer={sm.unpriced_assets.length ? <StaleChip /> : undefined} />
            <Card title="Unrealised profit or loss" info="On positions you still hold; realised profit is shown separately" as="article">
              <div className="flex flex-col gap-1 text-[length:var(--ws-font-size-headline)]">
                <SignedAmount value={sm.unrealized_pl.amount} currency={sm.currency} />
                <span className="text-[length:var(--ws-font-size-caption)] text-fg-muted">Realised: {formatMoney(sm.realized_pl.amount, sm.currency).text}</span>
              </div>
            </Card>
            <KpiCard label="Income, last 12 months" value={inc.yearly.amount} currency={inc.currency} footer={<span className="text-fg-muted">Monthly average {formatMoney(inc.monthly.amount, inc.currency).text}</span>} />
            <Card title="Goals" as="article">
              <p className="text-[length:var(--ws-font-size-headline)] font-semibold">
                {g.on_track} of {g.total} on track
              </p>
              <p className="mt-1 text-[length:var(--ws-font-size-caption)] text-fg-muted">{g.notice}</p>
            </Card>
          </div>
        ) : null}
      </Section>
      <RecentActivity />
    </div>
  );
}

function RecentActivity() {
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: () => apiGet<S["PortfolioOut"][]>("portfolios"), staleTime: STALE_MS });
  // The API lists portfolios oldest first; the three most recently created stand in for "recent".
  const active = (portfolios.data ?? []).filter((p) => !p.archived_at).slice(-3);
  const ledgers = useQueries({
    queries: active.map((p) => ({
      queryKey: ["transactions", p.id, "recent"],
      queryFn: () => apiGet<S["TransactionPage"]>(`portfolios/${p.id}/transactions?limit=5`),
      staleTime: STALE_MS,
    })),
  });
  if (portfolios.isPending || ledgers.some((l) => l.isPending)) return <Card title="Recent activity"><LoadingState label="Loading recent activity" /></Card>;
  if (portfolios.isError || ledgers.some((l) => l.isError)) return <Card title="Recent activity"><ErrorState message="Recent activity could not be loaded." onRetry={() => { void portfolios.refetch(); ledgers.forEach((l) => void l.refetch()); }} /></Card>;
  const rows = ledgers
    .flatMap((l, i) => (l.data?.items ?? []).map((t) => ({ t, portfolio: active[i].name })))
    .sort((a, b) => (a.t.trade_date < b.t.trade_date ? 1 : a.t.trade_date > b.t.trade_date ? -1 : 0))
    .slice(0, 6)
    .map(({ t, portfolio }) => ({
      id: t.id,
      date: t.trade_date,
      type: t.transaction_type.replaceAll("_", " "),
      portfolio,
      amount: t.gross_amount.amount,
      currency: t.gross_amount.currency,
    }));
  return (
    <Card title="Recent activity" actions={<Link href="/portfolio/transactions" className="font-semibold text-primary underline">All transactions</Link>}>
      {rows.length ? (
        <DataGrid
          caption="Recent transactions"
          rowKey="id"
          rows={rows}
          columns={[
            { key: "date", header: "Date", kind: "date" },
            { key: "type", header: "Type" },
            { key: "portfolio", header: "Portfolio" },
            { key: "amount", header: "Amount", kind: "money", currencyKey: "currency" },
          ]}
        />
      ) : (
        <EmptyState title="No transactions yet">Add an investment to start your ledger.</EmptyState>
      )}
    </Card>
  );
}

function Insights() {
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: () => apiGet<S["PortfolioOut"][]>("portfolios"), staleTime: STALE_MS });
  const first = (portfolios.data ?? []).find((p) => !p.archived_at);
  const doctor = useQuery({
    queryKey: ["doctor", first?.id],
    queryFn: () => apiPost<S["DoctorOut"]>("ai/portfolio-doctor", { portfolio_id: first?.id }),
    enabled: Boolean(first),
    staleTime: 5 * STALE_MS,
  });
  if (portfolios.isPending || (first && doctor.isPending)) return <Card title="Portfolio Doctor"><LoadingState label="Loading insights" /></Card>;
  if (portfolios.isError || doctor.isError) return <Card title="Portfolio Doctor"><ErrorState message="Insights could not be loaded." onRetry={() => { void portfolios.refetch(); void doctor.refetch(); }} /></Card>;
  const d = doctor.data;
  const flagged = (d?.findings ?? []).filter((f) => f.status === "flagged").slice(0, 3);
  return (
    <Card title="Portfolio Doctor" info="Deterministic observations against stated thresholds; not advice" actions={<Link href="/ai" className="font-semibold text-primary underline">Ask the Copilot</Link>}>
      {!first || !d ? (
        <EmptyState title="Nothing to review yet">The Portfolio Doctor looks at a portfolio once it has holdings.</EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-fg-muted">
            {first.name}: {flagged.length ? `${flagged.length} observation${flagged.length === 1 ? "" : "s"} worth a look.` : "no observations beyond the thresholds."}
          </p>
          {flagged.length ? (
            <ul className="flex flex-col gap-2">
              {flagged.map((f) => (
                <li key={`${f.check}-${f.subject ?? ""}`} className="rounded-[var(--ws-radius-control)] border border-divider p-3">
                  <span className="text-[length:var(--ws-font-size-caption)] font-semibold uppercase text-fg-muted">{f.severity} · {f.check.replaceAll("_", " ")}</span>
                  <p>{f.message}</p>
                </li>
              ))}
            </ul>
          ) : null}
          <DisclosurePanel title="About these observations" notices={[d.notice]} />
        </div>
      )}
    </Card>
  );
}

function GoalsSection() {
  const goals = useQuery({ queryKey: ["goals-summary"], queryFn: () => apiGet<S["GoalsSummaryOut"]>("goals/summary"), staleTime: STALE_MS });
  return (
    <Section title="Goals" query={goals}>
      <Card title="Goals" actions={<Link href="/goals" className="font-semibold text-primary underline">All goals</Link>}>
        {goals.data?.items.length ? (
          <ul className="flex flex-col gap-3">
            {goals.data.items.slice(0, 4).map((g) => (
              <li key={g.id}>
                <div className="flex flex-wrap items-center justify-between gap-x-2">
                  <span className="font-medium">{g.name}</span>
                  <span className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
                    {g.status.replaceAll("_", " ")} · {formatPercent(g.progress_percent, "en", 1)} of {formatMoney(g.target.amount, g.target.currency).text}
                  </span>
                </div>
                <div role="progressbar" aria-label={`${g.name} progress`} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Number.parseInt(g.progress_percent, 10)} className="mt-1 h-2 overflow-hidden rounded-full bg-divider">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, Number.parseInt(g.progress_percent, 10) || 0)}%` }} />
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No goals yet">Set a goal to track your progress towards it.</EmptyState>
        )}
        {goals.data ? <p className="mt-3 text-[length:var(--ws-font-size-caption)] text-fg-muted">{goals.data.notice}</p> : null}
      </Card>
    </Section>
  );
}

const WIDGETS: Record<Section, () => React.JSX.Element> = {
  wealthSummary: WealthSummary,
  metrics: Metrics,
  insight: Insights,
  goals: GoalsSection,
};

function Customise({ layout, onChange, onClose }: { layout: Layout; onChange: (l: Layout) => void; onClose: () => void }) {
  return (
    <Card title="Customise the dashboard" actions={<Button onClick={onClose}>Done</Button>}>
      <ul className="flex flex-col gap-2">
        {layout.order.map((s, i) => (
          <li key={s} className="flex flex-wrap items-center justify-between gap-2">
            <span>{SECTION_LABELS[s]}</span>
            <span className="flex gap-1">
              <IconButton icon="arrowUp" label={`Move ${SECTION_LABELS[s]} up`} disabled={i === 0} onClick={() => onChange(moveSection(layout, s, -1))} />
              <IconButton icon="arrowDown" label={`Move ${SECTION_LABELS[s]} down`} disabled={i === layout.order.length - 1} onClick={() => onChange(moveSection(layout, s, 1))} />
              <Button aria-pressed={!layout.hidden.includes(s)} onClick={() => onChange(toggleSection(layout, s))}>
                {layout.hidden.includes(s) ? "Show" : "Hide"}
                <span className="sr-only"> {SECTION_LABELS[s]}</span>
              </Button>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** The executive dashboard (P14-T07): every figure is the API's, in the reporting currency. */
export function Dashboard() {
  const online = useOnline();
  const queryClient = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: () => apiGet<S["MeResponse"]>("me"), staleTime: STALE_MS });
  const [editing, setEditing] = useState(false);
  const save = useMutation({
    mutationFn: (layout: Layout) => apiPatch<S["MeResponse"]>("me/preferences", { dashboard_layout: layout }),
    onSuccess: (data) => queryClient.setQueryData(["me"], data),
  });
  const layout = normaliseLayout(save.variables ?? me.data?.preferences?.dashboard_layout);
  const shown = visibleSections(layout);
  const first = (me.data?.display_name ?? me.data?.email ?? "there").split(/[ @]/)[0];
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">Home</h1>
          <p className="text-fg-muted">Hello, {first}. Here is where your wealth stands.</p>
        </div>
        <Button icon="table" onClick={() => setEditing((v) => !v)} aria-pressed={editing}>
          Customise
        </Button>
      </header>
      {!online ? <StatusBanner kind="warning">You are offline. The figures below are the last ones loaded; they are not updating.</StatusBanner> : null}
      {editing ? <Customise layout={layout} onChange={(l) => save.mutate(l)} onClose={() => setEditing(false)} /> : null}
      {save.isError ? <StatusBanner kind="warning">Your layout could not be saved to your account.</StatusBanner> : null}
      {me.isPending ? <LoadingState label="Loading your dashboard" lines={4} /> : shown.length ? shown.map((s) => { const W = WIDGETS[s]; return <W key={s} />; }) : <EmptyState title="Everything is hidden">Use Customise to show a section again.</EmptyState>}
      <StatusBanner kind="info">Informational only, not financial advice. WealthSphere never places trades.</StatusBanner>
    </div>
  );
}
