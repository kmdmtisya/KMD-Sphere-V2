"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import { formatPercent } from "@/lib/format/decimal";
import {
  defaultPlan,
  scenarioRequest,
  validatePlan,
  type PlanValues,
} from "@/lib/planning/forms";

import { Card } from "../cards/cards";
import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { DemoBadge } from "../figures/figures";
import { ScenarioResults } from "../planning/Calculator";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];

const dash = (v: string | null | undefined, suffix = "") =>
  v === null || v === undefined || v === "" ? "n/a" : `${v}${suffix}`;

/**
 * Compare and simulate (P14-T12.4): two to five instruments side by side with their past figures
 * (labelled past), explainable score and your eligibility; and a simulation under return rates you
 * enter yourself (there is no default return). Illustrations only: not forecasts, not advice.
 */
export function Compare() {
  const universe = useQuery({
    queryKey: ["universe", "", false],
    queryFn: () => apiGet<S["UniverseOut"]>("universe?eligible_only=false"),
    staleTime: 60_000,
  });
  const items = universe.data?.items ?? [];
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Compare instruments
        </h1>
        <p className="text-fg-muted">
          Side by side, with past figures labelled as past. Not a recommendation
          to buy or sell.
        </p>
      </header>
      <StatusBanner kind="info">
        Past performance does not predict future results. Scores describe
        measured characteristics, not expected returns.
      </StatusBanner>
      {universe.isPending ? <LoadingState label="Loading instruments" /> : null}
      {universe.isError ? (
        <ErrorState
          message="Instruments could not be loaded."
          onRetry={() => void universe.refetch()}
        />
      ) : null}
      {universe.data && items.length < 2 ? (
        <EmptyState title="Not enough instruments">
          At least two instruments are needed to compare.
        </EmptyState>
      ) : null}
      {items.length >= 2 ? (
        <>
          <Comparison items={items} />
          <Simulation items={items} />
        </>
      ) : null}
    </div>
  );
}

function Comparison({ items }: { items: S["InstrumentOut"][] }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: () =>
      apiPost<S["CompareOut"]>("ai/compare", { asset_ids: picked }),
    onMutate: () => setMessage(null),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The comparison was refused (${e.status}).`)
          : "The comparison could not be run. Try again.",
      ),
  });
  const toggle = (id: string) =>
    setPicked((p) =>
      p.includes(id)
        ? p.filter((x) => x !== id)
        : p.length < 5
          ? [...p, id]
          : p,
    );
  const out = run.data;
  return (
    <Card
      title="Choose two to five"
      info="Instruments in the investment universe"
    >
      <fieldset>
        <legend className="sr-only">Instruments to compare</legend>
        <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((i) => (
            <li key={i.asset_id}>
              <label className="flex min-h-9 items-center gap-2">
                <input
                  type="checkbox"
                  checked={picked.includes(i.asset_id)}
                  disabled={!picked.includes(i.asset_id) && picked.length >= 5}
                  onChange={() => toggle(i.asset_id)}
                />
                {i.name}
                {i.symbol ? ` (${i.symbol})` : ""}
                {i.is_demo ? " · DEMO" : ""}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
      <div className="mt-3 flex items-center gap-3">
        <Button
          variant="primary"
          disabled={picked.length < 2 || run.isPending}
          onClick={() => run.mutate()}
        >
          {run.isPending
            ? "Comparing…"
            : `Compare ${picked.length || ""} selected`.replace("  ", " ")}
        </Button>
        {picked.length < 2 ? (
          <span className="text-fg-muted">Choose at least two.</span>
        ) : null}
      </div>
      {message ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {out ? (
        <div className="mt-4 flex flex-col gap-3">
          <div className="overflow-x-auto">
            <table className="w-full text-start text-[length:var(--ws-font-size-label)]">
              <caption className="sr-only">Instruments compared</caption>
              <thead>
                <tr>
                  <th scope="col" className="p-2 text-start">
                    Measure
                  </th>
                  {out.items.map((c) => (
                    <th key={c.asset_id} scope="col" className="p-2 text-start">
                      {c.name} {c.is_demo ? <DemoBadge /> : null}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["Class", (c) => c.asset_class.replace(/_/g, " ")],
                    ["Currency", (c) => c.currency],
                    ["Risk level (1-5)", (c) => String(c.risk_level)],
                    ["Liquidity", (c) => c.liquidity],
                    [
                      "Expense ratio",
                      (c) =>
                        dash(
                          c.expense_ratio_percent
                            ? formatPercent(c.expense_ratio_percent)
                            : null,
                        ),
                    ],
                    [
                      "Past price change, last year (past)",
                      (c) =>
                        dash(
                          c.past.price_change_percent
                            ? formatPercent(c.past.price_change_percent)
                            : null,
                        ),
                    ],
                    [
                      "Past volatility (past)",
                      (c) =>
                        dash(
                          c.past.volatility_percent
                            ? formatPercent(c.past.volatility_percent)
                            : null,
                        ),
                    ],
                    [
                      "Past largest fall (past)",
                      (c) =>
                        dash(
                          c.past.max_drawdown_percent
                            ? formatPercent(c.past.max_drawdown_percent)
                            : null,
                        ),
                    ],
                    ["Score (0-100)", (c) => dash(c.score.score)],
                    ["Score confidence", (c) => c.score.confidence],
                    [
                      "Eligible for you",
                      (c) =>
                        c.eligible
                          ? "Yes"
                          : `No: ${c.eligibility_reasons.join(" ")}`,
                    ],
                  ] as [string, (c: S["ComparedOut"]) => string][]
                ).map(([label, value]) => (
                  <tr key={label} className="border-t border-divider">
                    <th scope="row" className="p-2 text-start font-semibold">
                      {label}
                    </th>
                    {out.items.map((c) => (
                      <td key={c.asset_id} className="p-2 tabular-nums">
                        {value(c)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DisclosurePanel
            title="About this comparison"
            notices={[
              out.notice ??
                "A comparison of measured characteristics, not a recommendation.",
            ]}
          />
        </div>
      ) : null}
    </Card>
  );
}

function Simulation({ items }: { items: S["InstrumentOut"][] }) {
  const [asset, setAsset] = useState("");
  // No default return: the rates are the user's own assumptions and start empty.
  const [values, setValues] = useState<PlanValues>({
    ...defaultPlan(),
    base: "",
    conservative: "",
    growth: "",
  });
  const [problems, setProblems] = useState<ReturnType<typeof validatePlan>>({});
  const [message, setMessage] = useState<string | null>(null);
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const instrument = items.find((i) => i.asset_id === asset) ?? items[0];
  const currency = prefs.data?.reporting_currency ?? instrument.currency;
  const set = (key: keyof PlanValues, value: string) =>
    setValues((v) => ({ ...v, [key]: value }));
  const run = useMutation({
    mutationFn: () =>
      apiPost<S["SimulateOut"]>("ai/simulate", {
        asset_id: instrument.asset_id,
        assumptions: scenarioRequest(values, currency),
      }),
    onMutate: () => setMessage(null),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The simulation was refused (${e.status}).`)
          : "The simulation could not be run. Try again.",
      ),
  });
  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validatePlan(values);
    setProblems(found);
    if (Object.keys(found).length === 0) run.mutate();
  }
  const field = (key: keyof PlanValues, label: string, hint?: string) => (
    <Field label={label} error={problems[key]} hint={hint}>
      {(p) => (
        <input
          {...p}
          inputMode="decimal"
          value={values[key]}
          onChange={(e) => set(key, e.target.value)}
        />
      )}
    </Field>
  );
  const out = run.data;
  return (
    <Card
      title="Simulate an instrument"
      info="Runs the deterministic forecast engine under the returns you enter"
    >
      <form
        onSubmit={submit}
        noValidate
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        <Field label="Instrument">
          {(p) => (
            <select
              {...p}
              value={instrument.asset_id}
              onChange={(e) => setAsset(e.target.value)}
            >
              {items.map((i) => (
                <option key={i.asset_id} value={i.asset_id}>
                  {i.name}
                </option>
              ))}
            </select>
          )}
        </Field>
        {field("initial", `Starting amount (${currency})`)}
        {field("contribution", `Contribution each month (${currency})`)}
        {field("years", "Years")}
        {field(
          "conservative",
          "Cautious return, % a year",
          "Your own assumption: there is no default",
        )}
        {field("base", "Base return, % a year")}
        {field("growth", "Optimistic return, % a year")}
        <div className="sm:col-span-2 lg:col-span-3">
          <Button type="submit" variant="primary" disabled={run.isPending}>
            {run.isPending ? "Simulating…" : "Simulate"}
          </Button>
        </div>
      </form>
      {message ? (
        <p role="alert" className="mt-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {out ? (
        <div className="mt-4 flex flex-col gap-3">
          {out.notes.length ? (
            <ul className="list-disc ps-5 text-fg-muted">
              {out.notes.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          ) : null}
          <ScenarioResults out={out.simulation} />
          <DisclosurePanel
            title="About this simulation"
            notices={[
              out.notice ??
                "An illustration under your assumptions, not a forecast.",
            ]}
          />
        </div>
      ) : null}
    </Card>
  );
}
