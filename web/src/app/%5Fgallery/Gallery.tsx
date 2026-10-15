"use client";

import { useState } from "react";

import { KpiCard, Card } from "@/components/cards/cards";
import { AllocationDonutChart } from "@/components/charts/AllocationDonutChart";
import { PerformanceLineChart } from "@/components/charts/PerformanceLineChart";
import { Button, IconButton, SegmentedControl } from "@/components/controls/controls";
import { DataGrid } from "@/components/data/DataGrid";
import {
  CalibrationBadge,
  ChangeIndicator,
  CurrencyAmount,
  DataAsOfLabel,
  DemoBadge,
  RiskLabel,
  SimulatedBadge,
  StaleChip,
} from "@/components/figures/figures";
import { DisclosurePanel, EmptyState, ErrorState, LoadingState, StatusBanner } from "@/components/states/states";

import * as demo from "./sample";

const PERIODS = [
  { value: "1W", label: "1W" },
  { value: "1M", label: "1M" },
  { value: "1Y", label: "1Y" },
  { value: "ALL", label: "All" },
] as const;

/** One copy of the gallery, rendered inside a light or dark token scope. */
export function GalleryPanel({ theme }: { theme: "light" | "dark" }) {
  const [period, setPeriod] = useState<(typeof PERIODS)[number]["value"]>("1M");
  return (
    <section
      data-theme-pref={theme}
      aria-label={`${theme === "light" ? "Light" : "Dark"} theme`}
      className="flex min-w-0 flex-col gap-6 bg-scaffold p-6 text-fg"
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            {theme === "light" ? "Light" : "Dark"} theme
          </h2>
          <p className="text-fg-muted">Executive dashboard composition (reference image 1), DEMO data.</p>
        </div>
        <DemoBadge />
      </header>

      {/* Sample dashboard composition, as in the reference: KPI column beside a wide chart. */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <KpiCard
          label="Total wealth"
          info="Everything you own, in your reporting currency"
          value={demo.totalWealth.value}
          currency={demo.CURRENCY}
          changePercent={demo.totalWealth.changePercent}
          changeAmount={demo.totalWealth.changeAmount}
          period="this year"
          footer={<DataAsOfLabel asOf="2026-10-09T16:00:00Z" />}
        />
        <PerformanceLineChart
          title="Wealth over time"
          info="Total wealth at each valuation date"
          points={demo.wealthSeries}
          currency={demo.CURRENCY}
          summary="DEMO: total wealth went from $138,520.10 on 9 September to $139,986.35 on 9 October."
          actions={<SegmentedControl label="Period" options={PERIODS} value={period} onChange={setPeriod} />}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="Net worth" value={demo.netWorth.value} currency={demo.CURRENCY} changePercent={demo.netWorth.changePercent} changeAmount={demo.netWorth.changeAmount} period="this month" />
        <KpiCard label="Monthly income" value={demo.income.value} currency={demo.CURRENCY} changePercent={demo.income.changePercent} period="vs last month" />
        <Card title="AI insight" info="Facts, calculations, assumptions and interpretation are shown separately">
          <p className="mb-3">DEMO: Listed shares are 52.4% of your portfolio, above the 50% you set as a limit.</p>
          <DisclosurePanel title="Assumptions and sources" notices={["Fact: allocation from your holdings as of 9 Oct.", "Interpretation: AI explanation; not advice."]} />
          <div className="mt-3">
            <Button variant="primary" icon="info">
              Ask Copilot
            </Button>
          </div>
        </Card>
      </div>

      <AllocationDonutChart
        title="Allocation by asset class"
        items={demo.allocation}
        currency={demo.CURRENCY}
        summary="DEMO: listed shares 52.4%, bonds 21.1%, money market 14.3%, property 8.6%, cash 3.6%."
      />

      <Card title="Holdings" actions={<IconButton icon="expand" label="Open holdings" />}>
        <DataGrid
          caption="DEMO holdings"
          rowKey="id"
          rows={demo.holdings}
          columns={[
            { key: "name", header: "Holding" },
            { key: "assetClass", header: "Asset class" },
            { key: "marketValue", header: "Market value", kind: "money", currencyKey: "currency" },
            { key: "asOf", header: "As of", kind: "date" },
          ]}
        />
      </Card>

      <Card title="Figures and labels">
        <div className="flex flex-wrap items-center gap-4">
          <CurrencyAmount value="325980.65" currency="USD" size="headline" />
          <ChangeIndicator percent="12.00" amount="39117.67" currency="USD" period="this year" />
          <ChangeIndicator percent="-3.25" />
          <ChangeIndicator percent="0.00" />
          <DemoBadge />
          <SimulatedBadge />
          <CalibrationBadge />
          <StaleChip since="9 Oct, 16:00" />
          <RiskLabel level="low" />
          <RiskLabel level="medium" />
          <RiskLabel level="high" />
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Loading">
          <LoadingState label="Loading holdings" />
        </Card>
        <Card title="Empty">
          <EmptyState title="No transactions yet">Add your first investment to see it here.</EmptyState>
        </Card>
        <Card title="Error">
          <ErrorState message="The portfolio could not be loaded." correlationId="c0ffee12-demo" onRetry={() => undefined} />
        </Card>
      </div>

      <div className="flex flex-col gap-2">
        <StatusBanner kind="stale">Prices are 2 days old; figures may not reflect current values.</StatusBanner>
        <StatusBanner kind="info">Informational only, not financial advice.</StatusBanner>
        <DisclosurePanel notices={demo.notices} />
      </div>

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon="arrowUp">
          Add transaction
        </Button>
        <Button>Export</Button>
        <Button variant="ghost">Cancel</Button>
        <Button disabled>Unavailable</Button>
      </div>
    </section>
  );
}

/**
 * Components that follow the chosen appearance (no fixed theme scope), so a change of Light, Dark or
 * System is visible on charts, tables and dialogs at once (P14-T25.4).
 */
export function FollowingPanel() {
  return (
    <section aria-label="Following your appearance" data-testid="following-panel" className="flex flex-col gap-4 bg-scaffold p-6 text-fg">
      <h2 className="text-[length:var(--ws-font-size-headline)] font-semibold">Following your appearance</h2>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <KpiCard label="Total wealth" value={demo.totalWealth.value} currency={demo.CURRENCY} changePercent={demo.totalWealth.changePercent} changeAmount={demo.totalWealth.changeAmount} period="this year" footer={<DemoBadge />} />
        <PerformanceLineChart
          title="Wealth over time (following)"
          points={demo.wealthSeries}
          currency={demo.CURRENCY}
          summary="DEMO: total wealth went from $138,520.10 on 9 September to $139,986.35 on 9 October."
        />
      </div>
      <dialog open aria-label="Example dialog" className="relative rounded-[var(--ws-radius-card)] border border-divider bg-surface-elevated p-4 text-fg">
        <p className="font-semibold">Example dialog</p>
        <p className="text-fg-muted">Dialogs use the same tokens, so they follow the appearance too.</p>
      </dialog>
    </section>
  );
}
