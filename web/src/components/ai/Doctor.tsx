"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import { formatMoney } from "@/lib/format/decimal";

import { Card } from "../cards/cards";
import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataAsOfLabel } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];
type Severity = S["Severity"];

const SEVERITY: Record<Severity, string> = {
  ok: "No concern",
  info: "For information",
  low: "Low",
  medium: "Medium",
  high: "High",
};
const ORDER: Severity[] = ["high", "medium", "low", "info", "ok"];

/**
 * The Portfolio Doctor (P14-T12.3): observations about one portfolio against stated thresholds,
 * each with its measured value, the threshold and the assumptions. The severities come from the
 * backend's deterministic checks; nothing here is an instruction to buy or sell.
 */
export function Doctor() {
  const [choice, setChoice] = useState<string | null>(null);
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  const [message, setMessage] = useState<string | null>(null);
  const run = useMutation({
    mutationFn: (portfolioId: string) =>
      apiPost<S["DoctorOut"]>("ai/portfolio-doctor", {
        portfolio_id: portfolioId,
      }),
    onMutate: () => setMessage(null),
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The check was refused (${e.status}).`)
          : "The check could not be run. Try again.",
      ),
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
      <EmptyState title="No portfolios to check">
        Create a portfolio and add transactions first.
      </EmptyState>
    );
  const selected = list.find((p) => p.id === choice) ?? list[0];
  const out = run.data?.portfolio_id === selected.id ? run.data : undefined;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <header>
        <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
          Portfolio Doctor
        </h1>
        <p className="text-fg-muted">
          Observations about concentration, currency, liquidity, volatility,
          drawdown, income and goals, against stated thresholds. Observations
          only: not advice, and nothing is traded.
        </p>
      </header>
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-56">
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
        <Button
          variant="primary"
          disabled={run.isPending}
          onClick={() => run.mutate(selected.id)}
        >
          {run.isPending
            ? "Checking…"
            : out
              ? "Check again"
              : "Check this portfolio"}
        </Button>
      </div>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {run.isPending ? <LoadingState label="Checking the portfolio" /> : null}
      {out ? (
        <Results out={out} />
      ) : !run.isPending ? (
        <p className="text-fg-muted">
          Select Check this portfolio to run the checks.
        </p>
      ) : null}
    </div>
  );
}

function Results({ out }: { out: S["DoctorOut"] }) {
  const findings = [...out.findings].sort(
    (a, b) => ORDER.indexOf(a.severity) - ORDER.indexOf(b.severity),
  );
  return (
    <div className="flex flex-col gap-4">
      <Card title="Overall" actions={<DataAsOfLabel asOf={out.as_of} />}>
        <p className="text-[length:var(--ws-font-size-title)] font-semibold">
          {SEVERITY[out.overall]}
        </p>
        <p className="text-fg-muted">
          {out.counts.high} high · {out.counts.medium} medium · {out.counts.low}{" "}
          low · {out.counts.info} for information. Portfolio value{" "}
          {formatMoney(out.total_value.amount, out.currency).text}.
        </p>
        {!out.complete ? (
          <div className="mt-3">
            <StatusBanner kind="stale">
              Some data is missing or unpriced, so some checks are incomplete.
            </StatusBanner>
          </div>
        ) : null}
      </Card>
      <Card title="Findings">
        <ul className="flex flex-col gap-3">
          {findings.map((f, i) => (
            <li
              key={i}
              className="flex flex-col gap-1 rounded-[var(--ws-radius-control)] border border-divider p-3"
            >
              <p className="font-semibold">
                {SEVERITY[f.severity]} · {f.check.replace(/_/g, " ")}
                {f.subject ? ` · ${f.subject}` : ""}
              </p>
              <p>{f.message}</p>
              {f.value !== null && f.value !== undefined ? (
                <p className="text-fg-muted tabular-nums">
                  Measured {f.value}
                  {f.unit ?? ""}
                  {f.threshold
                    ? ` against a threshold of ${f.threshold}${f.unit ?? ""}`
                    : ""}
                </p>
              ) : null}
              {f.assumptions.length ? (
                <p className="text-fg-muted">
                  Assumptions: {f.assumptions.join(" ")}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      </Card>
      {out.scenarios.length ? (
        <Card
          title="What if"
          info="Hypothetical changes to a measure, not trades and not recommendations"
        >
          <ul className="flex flex-col gap-3">
            {out.scenarios.map((s, i) => (
              <li
                key={i}
                className="rounded-[var(--ws-radius-control)] border border-divider p-3"
              >
                <p className="font-semibold">{s.description}</p>
                <p className="tabular-nums">
                  {s.measure.replace(/_/g, " ")}: {s.before ?? "n/a"} →{" "}
                  {s.after ?? "n/a"}
                </p>
                {s.assumptions.length ? (
                  <p className="text-fg-muted">{s.assumptions.join(" ")}</p>
                ) : null}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
      <DisclosurePanel title="About the Doctor" notices={[out.notice]} />
    </div>
  );
}
