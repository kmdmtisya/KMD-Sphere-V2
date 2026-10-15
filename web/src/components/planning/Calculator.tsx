"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import { formatMoney, formatPercent } from "@/lib/format/decimal";
import {
  defaultPlan,
  FREQUENCIES,
  scenarioRequest,
  validatePlan,
  type Frequency,
  type PlanValues,
} from "@/lib/planning/forms";

import { Card } from "../cards/cards";
import { ScenarioLineChart } from "../charts/ScenarioLineChart";
import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataAsOfLabel, SimulatedBadge } from "../figures/figures";
import {
  DisclosurePanel,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];
type Projection = S["ForecastProjection"];

const KINDS: { key: "conservative" | "base" | "growth"; label: string }[] = [
  { key: "conservative", label: "Cautious" },
  { key: "base", label: "Base" },
  { key: "growth", label: "Optimistic" },
];

/**
 * The compounding calculator and forecast scenarios (P14-T10.1, T10.2). The backend computes every
 * figure (QG-30.4); this page sends the inputs as decimal strings and shows what comes back, always
 * labelled a projection: never a guaranteed return.
 */
export function Calculator() {
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const currencies = useQuery({
    queryKey: ["currencies"],
    queryFn: () => apiGet<S["CurrencyOut"][]>("currencies"),
    staleTime: 3_600_000,
  });
  const [values, setValues] = useState<PlanValues>(defaultPlan);
  const [currency, setCurrency] = useState<string | null>(null);
  const [problems, setProblems] = useState<ReturnType<typeof validatePlan>>({});
  const [message, setMessage] = useState<string | null>(null);
  const chosen = currency ?? prefs.data?.reporting_currency ?? "USD";
  const set = <K extends keyof PlanValues>(key: K, value: PlanValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }));

  const run = useMutation({
    mutationFn: () =>
      apiPost<S["ScenarioForecastOut"]>(
        `forecasts/scenarios?reporting_currency=${prefs.data?.reporting_currency ?? chosen}`,
        scenarioRequest(values, chosen),
      ),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The calculation was refused (${e.status}).`)
          : "The calculation could not be completed. Try again.",
      ),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validatePlan(values);
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0) run.mutate();
  }

  if (prefs.isPending) return <LoadingState label="Loading your settings" />;
  if (prefs.isError)
    return (
      <ErrorState
        message="Your settings could not be loaded."
        onRetry={() => void prefs.refetch()}
      />
    );

  const out = run.data;
  const text = (
    field: keyof PlanValues,
    label: string,
    error?: string,
    hint?: string,
  ) => (
    <Field label={label} error={error} hint={hint}>
      {(p) => (
        <input
          {...p}
          inputMode="decimal"
          value={values[field]}
          onChange={(e) => set(field, e.target.value as never)}
        />
      )}
    </Field>
  );
  const frequency = (
    field: "contributionFrequency" | "compounding",
    label: string,
  ) => (
    <Field label={label}>
      {(p) => (
        <select
          {...p}
          value={values[field]}
          onChange={(e) => set(field, e.target.value as Frequency)}
        >
          {FREQUENCIES.map((f) => (
            <option key={f.value} value={f.value}>
              {f.label}
            </option>
          ))}
        </select>
      )}
    </Field>
  );

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Calculator
        </h1>
        <p className="text-fg-muted">
          See how money could grow with regular contributions under three
          assumed rates. These are projections, not promises.
        </p>
      </header>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,22rem)_1fr]">
        <Card title="Your assumptions">
          <form onSubmit={submit} noValidate className="flex flex-col gap-4">
            <Field label="Currency">
              {(p) => (
                <select
                  {...p}
                  value={chosen}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  {(currencies.data ?? [{ code: chosen, name: "" }]).map(
                    (c) => (
                      <option key={c.code} value={c.code}>
                        {c.code}
                      </option>
                    ),
                  )}
                </select>
              )}
            </Field>
            {text("initial", "Starting amount", problems.initial)}
            {text("contribution", "Contribution", problems.contribution)}
            {frequency("contributionFrequency", "How often you contribute")}
            {text("years", "Years", problems.years, "Whole years, 1 to 60.")}
            <fieldset className="flex flex-col gap-3">
              <legend className="mb-1 font-semibold">
                Yearly return, before fees (%)
              </legend>
              {text("conservative", "Cautious", problems.conservative)}
              {text("base", "Base", problems.base)}
              {text("growth", "Optimistic", problems.growth)}
            </fieldset>
            <details>
              <summary className="cursor-pointer font-semibold">
                More assumptions
              </summary>
              <div className="mt-3 flex flex-col gap-4">
                {text(
                  "inflation",
                  "Inflation (% a year)",
                  problems.inflation,
                  "Used to show values in today's money.",
                )}
                {text("fee", "Annual fee (%)", problems.fee)}
                {text(
                  "contributionGrowth",
                  "Contributions grow by (% a year)",
                  problems.contributionGrowth,
                )}
                {frequency("compounding", "Compounding")}
              </div>
            </details>
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
          {run.isPending ? <LoadingState label="Calculating" /> : null}
          {out ? <ScenarioResults out={out} /> : null}
          {!out && !run.isPending ? (
            <Card title="Results">
              <p className="text-fg-muted">
                Choose your assumptions and select Calculate. The backend works
                the figures out and they appear here.
              </p>
            </Card>
          ) : null}
          <TargetPlanner
            values={values}
            currency={chosen}
            reporting={prefs.data.reporting_currency}
          />
        </div>
      </div>
    </div>
  );
}

export function ScenarioResults({ out }: { out: S["ScenarioForecastOut"] }) {
  const lines = KINDS.map((k) => ({
    name: k.label,
    points: (out.scenarios[k.key] as Projection).nominal,
  }));
  const base = out.scenarios.base;
  return (
    <>
      <Card
        title="Projected value at the end"
        actions={
          <>
            <SimulatedBadge />
            <DataAsOfLabel asOf={out.as_of} />
          </>
        }
        info="Each scenario assumes a steady yearly rate. Real markets vary from year to year."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          {KINDS.map((k) => {
            const s = out.scenarios[k.key] as Projection;
            return (
              <section
                key={k.key}
                aria-label={`${k.label} scenario`}
                className="flex flex-col gap-1 rounded-[var(--ws-radius-control)] border border-divider p-3"
              >
                <h3 className="font-semibold text-fg-muted">
                  {k.label} · {formatPercent(s.annual_return_percent)} a year
                </h3>
                <p className="text-[length:var(--ws-font-size-title)] font-semibold tabular-nums">
                  {formatMoney(s.final_nominal.amount, out.currency).text}
                </p>
                <p className="text-fg-muted">
                  In today&apos;s money:{" "}
                  <span className="tabular-nums">
                    {formatMoney(s.final_real.amount, out.currency).text}
                  </span>
                </p>
                <p className="text-fg-muted">
                  You put in{" "}
                  <span className="tabular-nums">
                    {
                      formatMoney(s.total_contributions.amount, out.currency)
                        .text
                    }
                  </span>
                  ; growth{" "}
                  <span className="tabular-nums">
                    {formatMoney(s.total_growth.amount, out.currency).text}
                  </span>
                </p>
              </section>
            );
          })}
        </div>
        {out.in_reporting ? (
          <div className="mt-3">
            <StatusBanner kind="info">
              Base scenario in {out.in_reporting.currency}:{" "}
              {
                formatMoney(
                  out.in_reporting.final_nominal.amount,
                  out.in_reporting.currency,
                ).text
              }
              . {out.in_reporting.note}
            </StatusBanner>
          </div>
        ) : null}
      </Card>
      <ScenarioLineChart
        title="Growth by year"
        currency={out.currency}
        lines={lines}
        summary={`Projected value over ${base.nominal.length - 1} years in three scenarios, ending at ${KINDS.map((k) => `${k.label.toLowerCase()} ${formatMoney((out.scenarios[k.key] as Projection).final_nominal.amount, out.currency).text}`).join(", ")}.`}
      />
      <DisclosurePanel title="About this projection" notices={[out.notice]} />
    </>
  );
}

/** How much to put in each period to reach a target (the backend's goal solver). */
function TargetPlanner({
  values,
  currency,
  reporting,
}: {
  values: PlanValues;
  currency: string;
  reporting: string;
}) {
  const [target, setTarget] = useState("100000");
  const [todays, setTodays] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () =>
      apiPost<S["GoalForecastOut"]>(
        `forecasts/goal?reporting_currency=${reporting}`,
        {
          initial_investment: { amount: values.initial, currency },
          annual_return_percent: values.base,
          years: Number(values.years),
          target: { amount: target, currency },
          target_in_todays_money: todays,
          inflation_percent: values.inflation,
          annual_fee_percent: values.fee,
          contribution_frequency: values.contributionFrequency,
          contribution_growth_percent: values.contributionGrowth,
          compounding_frequency: values.compounding,
        },
      ),
    onError: (e) =>
      setError(
        e instanceof ApiError
          ? (e.detail ?? `Refused (${e.status}).`)
          : "This could not be worked out. Try again.",
      ),
  });
  const valid = /^\d{1,20}(\.\d{1,12})?$/.test(target) && /[1-9]/.test(target);
  const out = run.data;
  return (
    <Card
      title="Reach a target"
      info="Uses the starting amount, years and base rate above"
    >
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48">
          <Field
            label={`Target amount (${currency})`}
            error={target && !valid ? "Enter an amount above zero." : undefined}
          >
            {(p) => (
              <input
                {...p}
                inputMode="decimal"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            )}
          </Field>
        </div>
        <label className="flex min-h-9 items-center gap-2">
          <input
            type="checkbox"
            checked={todays}
            onChange={(e) => setTodays(e.target.checked)}
          />
          In today&apos;s money
        </label>
        <Button
          variant="primary"
          disabled={
            !valid ||
            run.isPending ||
            Object.keys(validatePlan(values)).length > 0
          }
          onClick={() => {
            setError(null);
            run.mutate();
          }}
        >
          {run.isPending ? "Working it out…" : "Work out the contribution"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          {error}
        </p>
      ) : null}
      {out ? (
        <div className="mt-3" aria-live="polite">
          {out.reached_without_contributions ? (
            <p>
              Your starting amount alone is projected to reach this target, with
              no further contributions.
            </p>
          ) : (
            <p>
              To reach it, you would need to contribute about{" "}
              <strong className="tabular-nums">
                {
                  formatMoney(out.required_contribution.amount, out.currency)
                    .text
                }
              </strong>{" "}
              each{" "}
              {values.contributionFrequency === "yearly"
                ? "year"
                : values.contributionFrequency === "quarterly"
                  ? "quarter"
                  : "month"}
              , if the base rate holds.
            </p>
          )}
          <div className="mt-2">
            <DisclosurePanel
              title="About this estimate"
              notices={[out.notice]}
            />
          </div>
        </div>
      ) : null}
    </Card>
  );
}
