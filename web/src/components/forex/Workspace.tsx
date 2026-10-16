"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import {
  emptyRisk,
  riskRequest,
  validateRisk,
  type RiskValues,
} from "@/lib/forex/forms";

import { ChatPane } from "../ai/ChatPane";
import { Card } from "../cards/cards";
import { CandleChart } from "../charts/CandleChart";
import { Button, SegmentedControl } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import {
  CalibrationBadge,
  DataAsOfLabel,
  DemoBadge,
  SimulatedBadge,
  StaleChip,
} from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";
import { Paper } from "./Paper";

type S = components["schemas"];

const TABS = [
  { value: "analysis", label: "Analysis" },
  { value: "opportunities", label: "Opportunities" },
  { value: "risk", label: "Risk calculator" },
  { value: "calendar", label: "Calendar" },
  { value: "paper", label: "Paper trading" },
  { value: "backtests", label: "Backtests" },
  { value: "copilot", label: "Copilot" },
] as const;
type Tab = (typeof TABS)[number]["value"];

const FEED: Record<string, string> = {
  connected: "Feed connected",
  degraded: "Feed degraded: quotes may be late",
  disconnected: "Feed disconnected: nothing here is current",
};
const FOREX_SUGGESTIONS = [
  "What is the current state of EUR/USD?",
  "Explain the top ranked forex setup and its risks",
  "What events could move the dollar this week?",
  "How is my paper trading account doing?",
];
const label = (s: string) => s.replace(/_/g, " ");
const DAYS: Record<string, number> = { "15m": 2, "1H": 7, "4H": 30, "1D": 180 };

/**
 * The advanced forex workspace (P14-T24), shown only where the forex module is on. Every price,
 * forecast and score names its data type, time and feed status; a forecast says when its
 * probability is not yet calibrated; PAPER TRADING is always labelled and uses fictional money that
 * never appears in your wealth figures. There is no way to place a real-money order here.
 */
export function Workspace() {
  const [tab, setTab] = useState<Tab>("analysis");
  const quotes = useQuery({
    queryKey: ["forex-quotes-status"],
    queryFn: () => apiGet<S["QuotesOut"]>("forex/quotes"),
    staleTime: 15_000,
  });
  const feed = quotes.data?.feed_status;
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Forex workspace
          </h1>
          <p className="text-fg-muted">
            Analysis, ranked research setups, a risk calculator, the calendar
            and a paper-trading account. Research and simulation only.
          </p>
        </div>
        <SegmentedControl
          label="Panel"
          options={TABS}
          value={tab}
          onChange={setTab}
        />
      </header>
      <StatusBanner kind={feed && feed !== "connected" ? "stale" : "info"}>
        <span role="status">
          This workspace places no real trades and gives no advice.{" "}
          {feed ? `${FEED[feed] ?? feed}. ` : ""}
          {quotes.data ? `Data provider: ${quotes.data.provider}. ` : ""}
          Forecasts and scores are model outputs, not predictions or guarantees.
        </span>
      </StatusBanner>
      {tab === "analysis" ? <Analysis /> : null}
      {tab === "opportunities" ? <Opportunities /> : null}
      {tab === "risk" ? <RiskCalculator /> : null}
      {tab === "calendar" ? <Calendar /> : null}
      {tab === "paper" ? <Paper /> : null}
      {tab === "backtests" ? <Backtests /> : null}
      {tab === "copilot" ? (
        <Card
          title="Forex Copilot"
          info="The same assistant, asked about forex. It reads your data through allow-listed tools and never places orders"
        >
          <ChatPane suggestions={FOREX_SUGGESTIONS} />
        </Card>
      ) : null}
    </div>
  );
}

function useInstruments() {
  return useQuery({
    queryKey: ["forex-instruments"],
    queryFn: () => apiGet<S["InstrumentsOut"]>("forex/instruments"),
    staleTime: 300_000,
  });
}

function PairSelect({
  labelText = "Pair",
  value,
  onChange,
}: {
  labelText?: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const instruments = useInstruments();
  return (
    <Field label={labelText}>
      {(p) => (
        <select {...p} value={value} onChange={(e) => onChange(e.target.value)}>
          {(
            instruments.data?.items ?? [
              { code: value, base: value.slice(0, 3), quote: value.slice(4) },
            ]
          ).map((i) => (
            <option key={i.code} value={i.code}>
              {i.base}/{i.quote}
            </option>
          ))}
        </select>
      )}
    </Field>
  );
}

function DataTypes({ types }: { types: string[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {types.map((t) =>
        t.includes("simulated") ? (
          <SimulatedBadge key={t} />
        ) : t.includes("demo") ? (
          <DemoBadge key={t} />
        ) : (
          <span
            key={t}
            className="rounded-[var(--ws-radius-pill)] border border-line px-2 py-0.5 text-[length:var(--ws-font-size-caption)] font-semibold uppercase"
          >
            {label(t)}
          </span>
        ),
      )}
    </span>
  );
}

function Analysis() {
  const [pair, setPair] = useState("EUR_USD");
  const [timeframe, setTimeframe] = useState<"15m" | "1H" | "4H" | "1D">("1H");
  const [horizon, setHorizon] = useState<S["ForecastOut"]["horizon"]>("4h");
  const end = new Date();
  const start = new Date(end.getTime() - DAYS[timeframe] * 86_400_000);
  const range = `instrument=${pair}&timeframe=${timeframe}&start=${start.toISOString()}&end=${end.toISOString()}`;
  const candles = useQuery({
    queryKey: ["forex-candles", pair, timeframe],
    queryFn: () => apiGet<S["CandlesOut"]>(`forex/candles?${range}`),
    staleTime: 30_000,
  });
  const indicators = useQuery({
    queryKey: ["forex-indicators", pair, timeframe],
    queryFn: () =>
      apiGet<S["IndicatorsOut"]>(
        `forex/indicators?${range}&indicator=sma:20&indicator=ema:50`,
      ),
    staleTime: 30_000,
  });
  const forecast = useQuery({
    queryKey: ["forex-forecast", pair, horizon],
    queryFn: () =>
      apiGet<S["ForecastOut"]>(
        `forex/forecasts?instrument=${pair}&horizon=${horizon}`,
      ),
    staleTime: 60_000,
  });
  const c = candles.data;
  const lines = (indicators.data?.series ?? []).flatMap((s) => {
    const out = Object.entries(
      s.outputs as Record<string, (string | null)[]>,
    ).find(([, v]) => Array.isArray(v));
    return out ? [{ name: s.name, values: out[1] }] : [];
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-40">
          <PairSelect value={pair} onChange={setPair} />
        </div>
        <SegmentedControl
          label="Candle size"
          options={
            [
              { value: "15m", label: "15m" },
              { value: "1H", label: "1H" },
              { value: "4H", label: "4H" },
              { value: "1D", label: "1D" },
            ] as const
          }
          value={timeframe}
          onChange={setTimeframe}
        />
        {c ? (
          <DataTypes types={[...new Set(c.items.map((i) => i.data_type))]} />
        ) : null}
      </div>
      {candles.isPending ? (
        <Card title="Price">
          <LoadingState label="Loading candles" reserve="22rem" />
        </Card>
      ) : null}
      {candles.isError ? (
        <Card title="Price">
          <ErrorState
            message="Candles could not be loaded."
            onRetry={() => void candles.refetch()}
          />
        </Card>
      ) : null}
      {c && c.items.length === 0 ? (
        <Card title="Price">
          <EmptyState title="No candles">
            No price history is stored for this pair and candle size in the last{" "}
            {DAYS[timeframe]} days.
          </EmptyState>
        </Card>
      ) : null}
      {c && c.items.length > 0 ? (
        <>
          <CandleChart
            title={`${pair.replace("_", "/")} · ${timeframe} candles`}
            info={`${c.price_basis} prices from ${c.provider}${c.truncated ? "; showing the most recent candles" : ""}. Indicators: SMA 20 and EMA 50.`}
            candles={c.items}
            indicators={lines}
            summary={`${c.items.length} ${timeframe} candles of ${pair.replace("_", "/")} from ${c.items[0].ts.slice(0, 16)} to ${c.items[c.items.length - 1].ts.slice(0, 16)}; last close ${c.items[c.items.length - 1].close}.`}
          />
          <p className="text-fg-muted">{c.notice}</p>
        </>
      ) : null}
      <Card
        title="Forecast"
        info="A statistical estimate from past prices; not a prediction, not advice, never a guaranteed return"
        actions={
          <SegmentedControl
            label="Horizon"
            options={
              [
                { value: "15m", label: "15m" },
                { value: "1h", label: "1h" },
                { value: "4h", label: "4h" },
                { value: "24h", label: "24h" },
                { value: "1w", label: "1w" },
              ] as const
            }
            value={horizon}
            onChange={setHorizon}
          />
        }
      >
        {forecast.isPending ? (
          <LoadingState label="Loading the forecast" lines={2} reserve="9rem" />
        ) : null}
        {forecast.isError ? (
          <ErrorState
            message="The forecast could not be loaded."
            onRetry={() => void forecast.refetch()}
          />
        ) : null}
        {forecast.data?.status === "unavailable" ? (
          <p className="text-fg-muted">
            No forecast is available for this pair and horizon
            {forecast.data.reason ? `: ${forecast.data.reason}` : ""}.
          </p>
        ) : null}
        {forecast.data?.status === "available" && forecast.data.forecast ? (
          <ForecastView out={forecast.data} />
        ) : null}
      </Card>
    </div>
  );
}

function ForecastView({ out }: { out: S["ForecastOut"] }) {
  const f = out.forecast!;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <DataAsOfLabel asOf={f.as_of} />
        {!f.fresh ? <StaleChip since={f.as_of} /> : null}
        {f.probability_label === "Requires calibration" ? (
          <CalibrationBadge />
        ) : (
          <span className="font-semibold">Calibrated</span>
        )}
        <DataTypes types={f.data_types} />
      </div>
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Last close" value={f.last_close} />
        <Stat label="Median price at the horizon" value={f.price_median} />
        <Stat label="Chance of a higher price (model)" value={`${f.prob_up}`} />
        <Stat
          label="Chance of a lower price (model)"
          value={`${f.prob_down}`}
        />
        <Stat
          label="Likely range (50%)"
          value={`${f.price_interval_50.low} to ${f.price_interval_50.high}`}
        />
        <Stat
          label="Likely range (80%)"
          value={`${f.price_interval_80.low} to ${f.price_interval_80.high}`}
        />
        <Stat label="Expected volatility" value={f.expected_volatility} />
        <Stat
          label="Volatility model"
          value={f.volatility_model.toUpperCase()}
        />
      </dl>
      <p className="text-fg-muted">
        {f.probability_note} {out.notice}
      </p>
    </div>
  );
}

function Stat({ label: text, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {text}
      </dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function Opportunities() {
  const [timeframe, setTimeframe] =
    useState<S["RankingOut"]["timeframe"]>("1H");
  const ranking = useQuery({
    queryKey: ["forex-opportunities", timeframe],
    queryFn: () =>
      apiGet<S["RankingOut"]>(`forex/opportunities?timeframe=${timeframe}`),
    staleTime: 30_000,
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <SegmentedControl
          label="Timeframe"
          options={
            [
              { value: "5m", label: "5m" },
              { value: "15m", label: "15m" },
              { value: "1H", label: "1H" },
              { value: "4H", label: "4H" },
              { value: "1D", label: "1D" },
            ] as const
          }
          value={timeframe}
          onChange={setTimeframe}
        />
        {ranking.data ? <DataAsOfLabel asOf={ranking.data.as_of} /> : null}
      </div>
      {ranking.isPending ? (
        <LoadingState label="Ranking setups" reserve="20rem" />
      ) : null}
      {ranking.isError ? (
        <ErrorState
          message="The ranking could not be loaded."
          onRetry={() => void ranking.refetch()}
        />
      ) : null}
      {ranking.data && ranking.data.items.length === 0 ? (
        <EmptyState title="No setups right now">
          No pair meets the rules on this timeframe, or there is not enough
          fresh data. Nothing is invented to fill the list.
        </EmptyState>
      ) : null}
      {ranking.data && ranking.data.items.length > 0 ? (
        <ul className="grid gap-4 xl:grid-cols-2">
          {ranking.data.items.map((o) => (
            <li key={`${o.instrument}-${o.rank}`}>
              <Card
                title={`${o.rank ?? "-"}. ${o.instrument.replace("_", "/")} · ${o.scenario}`}
                as="article"
                actions={<DataTypes types={o.freshness.data_types} />}
              >
                <p className="mb-3 text-fg-muted">
                  {label(o.opportunity_type)} · {label(o.market_condition)} ·{" "}
                  {o.tier} pair · risk {label(o.risk)} · score {o.score}
                </p>
                <dl className="grid gap-3 sm:grid-cols-3">
                  <Stat label="Entry" value={o.levels.entry} />
                  <Stat label="Stop" value={o.levels.stop} />
                  <Stat label="Target" value={o.levels.target} />
                  <Stat label="Risk (pips)" value={o.levels.risk_pips} />
                  <Stat label="Reward (pips)" value={o.levels.reward_pips} />
                  <Stat label="Reward to risk" value={o.levels.risk_reward} />
                </dl>
                <p className="mt-3 text-fg-muted">
                  Spread {o.costs.spread_pips ?? "n/a"} pips
                  {o.costs.spread_share_of_risk
                    ? `, ${o.costs.spread_share_of_risk} of the risk`
                    : ""}
                  . Data as of{" "}
                  {o.freshness.bar_as_of.slice(0, 16).replace("T", " ")} (
                  {o.freshness.bar_age_seconds}s old).
                </p>
                {o.forecast ? (
                  <p className="mt-2 text-fg-muted">
                    Forecast ({o.forecast.horizon}): chance of up{" "}
                    {o.forecast.prob_up} · {o.forecast.calibration}.
                  </p>
                ) : null}
                <h3 className="mt-3 font-semibold">Risks</h3>
                <ul className="list-disc ps-5">
                  {o.risks.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <h3 className="mt-3 font-semibold">Assumptions</h3>
                <ul className="list-disc ps-5">
                  {o.assumptions.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
                <details className="mt-3">
                  <summary className="cursor-pointer font-semibold">
                    How the score was made
                  </summary>
                  <ul className="mt-2 list-disc ps-5">
                    {o.factors.map((f) => (
                      <li key={f.name}>
                        {label(f.name)}: {f.value} (weight {f.weight}, adds{" "}
                        {f.contribution}). {f.detail}
                      </li>
                    ))}
                  </ul>
                  {o.adjustments.length ? (
                    <p className="mt-2 text-fg-muted">
                      Adjustments: {o.adjustments.join("; ")}
                    </p>
                  ) : null}
                  <p className="mt-2 text-fg-muted">
                    Rule {o.rule} version {o.rule_version}. Evidence:{" "}
                    {o.evidence.join("; ") || "none recorded"}.
                  </p>
                </details>
                <p className="mt-3 text-[length:var(--ws-font-size-caption)] text-fg-muted">
                  A research scenario, not an order and not advice.
                </p>
              </Card>
            </li>
          ))}
        </ul>
      ) : null}
      {ranking.data ? (
        <DisclosurePanel
          title="About the ranking"
          notices={[ranking.data.notice]}
        />
      ) : null}
    </div>
  );
}

function RiskCalculator() {
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const [values, setValues] = useState<RiskValues | null>(null);
  const v = values ?? emptyRisk(prefs.data?.reporting_currency ?? "USD");
  const [problems, setProblems] = useState<ReturnType<typeof validateRisk>>({});
  const [message, setMessage] = useState<string | null>(null);
  const set = <K extends keyof RiskValues>(key: K, value: RiskValues[K]) =>
    setValues({ ...v, [key]: value });
  const run = useMutation({
    mutationFn: () =>
      apiPost<S["ForexRiskOut"]>("forex/risk/calculate", riskRequest(v)),
    onMutate: () => setMessage(null),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The calculation was refused (${e.status}).`)
          : "The calculation could not be completed. Try again.",
      ),
  });
  const text = (key: keyof RiskValues, labelText: string, hint?: string) => (
    <Field label={labelText} error={problems[key]} hint={hint}>
      {(p) => (
        <input
          {...p}
          inputMode="decimal"
          value={v[key]}
          onChange={(e) => set(key, e.target.value as never)}
        />
      )}
    </Field>
  );
  const out = run.data;
  return (
    <div className="grid gap-4 lg:grid-cols-[minmax(0,24rem)_1fr]">
      <Card
        title="Position risk"
        info="How big a position would risk the share of your balance you choose; calculated by the backend"
      >
        <form
          noValidate
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            const found = validateRisk(v);
            setProblems(found);
            if (Object.keys(found).length === 0) run.mutate();
          }}
        >
          <PairSelect
            value={v.instrument}
            onChange={(x) => set("instrument", x)}
          />
          <SegmentedControl
            label="Direction"
            options={
              [
                { value: "long", label: "Long" },
                { value: "short", label: "Short" },
              ] as const
            }
            value={v.direction}
            onChange={(x) => set("direction", x)}
          />
          {text("entry", "Entry price")}
          {text("stop", "Stop price")}
          {text("target", "Target price (optional)")}
          {text("balance", `Account balance (${v.currency})`)}
          {text("riskPercent", "Risk per trade (% of balance)")}
          {message ? (
            <p role="alert" className="font-semibold text-negative-text">
              {message}
            </p>
          ) : null}
          <Button type="submit" variant="primary" disabled={run.isPending}>
            {run.isPending ? "Calculating…" : "Calculate"}
          </Button>
        </form>
      </Card>
      <div className="flex flex-col gap-4">
        {!out ? (
          <Card title="Result">
            <p className="text-fg-muted">
              Enter a pair, an entry and a stop, then calculate. The size, the
              cost, the margin and the effect on your account come from the
              backend.
            </p>
          </Card>
        ) : null}
        {out ? (
          <>
            {out.warnings.length ? (
              <StatusBanner kind="stale">{out.warnings.join(" ")}</StatusBanner>
            ) : null}
            <Card
              title="Size and cost"
              info={
                out.specification.version
                  ? `Contract specification version ${out.specification.version}`
                  : undefined
              }
            >
              <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                <Stat
                  label="Position size"
                  value={`${out.size.lots} lots (${out.size.units} units)`}
                />
                <Stat label="Sizing status" value={label(out.size.status)} />
                <Stat
                  label="Pip value per lot"
                  value={`${out.pip_value.per_lot_account_currency} ${out.account_currency}`}
                />
                <Stat
                  label="Amount at risk"
                  value={`${out.outcome.risk_amount} ${out.account_currency}`}
                />
                <Stat
                  label="Loss at the stop, after costs"
                  value={`${out.outcome.loss_after_costs} ${out.account_currency}`}
                />
                <Stat
                  label="Profit at the target, after costs"
                  value={
                    out.outcome.profit_after_costs
                      ? `${out.outcome.profit_after_costs} ${out.account_currency}`
                      : "No target given"
                  }
                />
                <Stat
                  label="Reward to risk (after costs)"
                  value={out.outcome.risk_reward_after_costs ?? "n/a"}
                />
                <Stat
                  label="Costs (spread, slippage, commission)"
                  value={`${out.costs.total} ${out.account_currency}`}
                />
                <Stat
                  label="Margin needed"
                  value={`${out.margin.margin} ${out.account_currency} (${out.margin.margin_use_percent}% of balance)`}
                />
                <Stat
                  label="Leverage of this position"
                  value={`${out.margin.position_leverage}x (limit ${out.margin.max_leverage}x)`}
                />
                <Stat
                  label="Effect on the account at the stop"
                  value={`${out.account_impact_percent}%`}
                />
              </dl>
            </Card>
            <DisclosurePanel
              title="About this calculation"
              notices={[out.notice, ...out.disclosures]}
            />
          </>
        ) : null}
      </div>
    </div>
  );
}

function Calendar() {
  const [importance, setImportance] = useState<"low" | "medium" | "high">(
    "medium",
  );
  const start = new Date();
  const end = new Date(start.getTime() + 7 * 86_400_000);
  const events = useQuery({
    queryKey: ["forex-calendar", importance],
    queryFn: () =>
      apiGet<S["CalendarOut"]>(
        `forex/calendar?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&min_importance=${importance}`,
      ),
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-4">
      <SegmentedControl
        label="Show events of at least"
        options={
          [
            { value: "low", label: "Low" },
            { value: "medium", label: "Medium" },
            { value: "high", label: "High" },
          ] as const
        }
        value={importance}
        onChange={setImportance}
      />
      {events.isPending ? (
        <LoadingState label="Loading the calendar" reserve="14rem" />
      ) : null}
      {events.isError ? (
        <ErrorState
          message="The calendar could not be loaded."
          onRetry={() => void events.refetch()}
        />
      ) : null}
      {events.data && events.data.items.length === 0 ? (
        <EmptyState title="No events">
          No events of this importance in the next seven days.
        </EmptyState>
      ) : null}
      {events.data && events.data.items.length > 0 ? (
        <Card title={`The next seven days (${events.data.timezone})`}>
          <DataGrid
            caption="Economic calendar"
            rowKey="id"
            rows={events.data.items.map((e) => ({
              id: e.id,
              when: e.scheduled_local.slice(0, 16).replace("T", " "),
              name: e.is_demo ? `${e.name} (DEMO)` : e.name,
              importance: e.importance,
              currencies: e.currencies.join(", "),
              source: e.source,
            }))}
            columns={[
              { key: "when", header: "Time" },
              { key: "name", header: "Event" },
              { key: "importance", header: "Importance" },
              { key: "currencies", header: "Currencies" },
              { key: "source", header: "Source" },
            ]}
          />
        </Card>
      ) : null}
      {events.data ? (
        <DisclosurePanel
          title="About the calendar"
          notices={[events.data.notice]}
        />
      ) : null}
    </div>
  );
}

function Backtests() {
  const list = useQuery({
    queryKey: ["forex-backtests"],
    queryFn: () => apiGet<S["ForexBacktestsOut"]>("forex/backtests?limit=50"),
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-4">
      {list.isPending ? (
        <LoadingState label="Loading backtests" reserve="12rem" />
      ) : null}
      {list.isError ? (
        <ErrorState
          message="Backtests could not be loaded."
          onRetry={() => void list.refetch()}
        />
      ) : null}
      {list.data && list.data.items.length === 0 ? (
        <EmptyState title="No backtests">
          No strategy backtest has been run yet.
        </EmptyState>
      ) : null}
      {list.data && list.data.items.length > 0 ? (
        <Card
          title="Strategy backtests"
          info="Past results on stored prices, tested on data the rule had not seen (out of sample)"
        >
          <DataGrid
            caption="Backtests"
            rowKey="id"
            rows={list.data.items.map((b) => ({
              id: b.id,
              label: b.label,
              pair: b.instrument.replace("_", "/"),
              tf: b.timeframe,
              period: `${b.period_start.slice(0, 10)} to ${b.period_end.slice(0, 10)}`,
              trades: String(b.out_of_sample_trades),
              ret: b.out_of_sample_return,
              pf: b.out_of_sample_profit_factor ?? "n/a",
              audit: b.leakage_audit_passed ? "Passed" : "Failed",
              kinds: b.data_types.join(", "),
            }))}
            columns={[
              { key: "label", header: "Backtest" },
              { key: "pair", header: "Pair" },
              { key: "tf", header: "Candle" },
              { key: "period", header: "Period" },
              { key: "trades", header: "Out-of-sample trades", align: "end" },
              { key: "ret", header: "Out-of-sample return", align: "end" },
              { key: "pf", header: "Profit factor", align: "end" },
              { key: "audit", header: "Leakage audit" },
              { key: "kinds", header: "Data" },
            ]}
          />
        </Card>
      ) : null}
      {list.data ? (
        <DisclosurePanel
          title="About backtests"
          notices={[
            list.data.notice,
            "A backtest describes the past on stored prices. It does not predict future results.",
          ]}
        />
      ) : null}
    </div>
  );
}
