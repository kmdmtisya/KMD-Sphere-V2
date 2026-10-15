"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";

import { Card } from "../cards/cards";
import { Button, SegmentedControl } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { DataAsOfLabel, DemoBadge } from "../figures/figures";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];

const TABS = [
  { value: "opportunities", label: "Opportunities" },
  { value: "universe", label: "Universe" },
  { value: "research", label: "Research" },
] as const;
type Tab = (typeof TABS)[number]["value"];

const AMOUNT = /^\d{1,12}(\.\d{1,2})?$/;

/**
 * Investment intelligence (P14-T12.4, T12.5): research candidates the backend filtered by your
 * eligibility and scored on measured characteristics, the investment universe, and the research
 * evidence. Each candidate carries its risks, assumptions and evidence; nothing is a recommendation
 * to trade, no return is promised, and demonstration data is labelled DEMO.
 */
export function Opportunities() {
  const [tab, setTab] = useState<Tab>("opportunities");
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">
            Opportunities
          </h1>
          <p className="text-fg-muted">
            Candidates to research, not recommendations. Scores describe
            measured characteristics and are not forecasts of return.
          </p>
        </div>
        <SegmentedControl
          label="Section"
          options={TABS}
          value={tab}
          onChange={setTab}
        />
      </header>
      <StatusBanner kind="info">
        Investing involves risk, including loss of capital. Nothing here is
        personal investment advice, and WealthSphere never places trades.
      </StatusBanner>
      {tab === "opportunities" ? <Candidates /> : null}
      {tab === "universe" ? <Universe /> : null}
      {tab === "research" ? <Research /> : null}
    </div>
  );
}

function Candidates() {
  const queryClient = useQueryClient();
  const [portfolioId, setPortfolioId] = useState("");
  const [assetClass, setAssetClass] = useState("");
  const [amount, setAmount] = useState("");
  const [limit, setLimit] = useState("3");
  const [message, setMessage] = useState<string | null>(null);
  const [shown, setShown] = useState<S["RunOut"] | null>(null);
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: false }],
    queryFn: () =>
      apiGet<S["PortfolioOut"][]>("portfolios?include_archived=false"),
    staleTime: 30_000,
  });
  const classes = useQuery({
    queryKey: ["asset-classes"],
    queryFn: () => apiGet<S["AssetClassOut"][]>("asset-classes"),
    staleTime: 3_600_000,
  });
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const runs = useQuery({
    queryKey: ["opportunity-runs"],
    queryFn: () =>
      apiGet<S["RunSummaryOut"][]>("ai/opportunities/runs?limit=10"),
    staleTime: 30_000,
  });
  const currency =
    portfolios.data?.find((p) => p.id === portfolioId)?.base_currency ??
    prefs.data?.reporting_currency ??
    "USD";
  const amountOk = amount === "" || AMOUNT.test(amount);

  const run = useMutation({
    mutationFn: () =>
      apiPost<S["RunOut"]>("ai/opportunities", {
        portfolio_id: portfolioId || null,
        asset_class: assetClass || null,
        amount: amount ? { amount, currency } : null,
        limit: Number(limit),
      }),
    onMutate: () => setMessage(null),
    onSuccess: (out) => {
      setShown(out);
      void queryClient.invalidateQueries({ queryKey: ["opportunity-runs"] });
    },
    onError: (e) =>
      setMessage(
        e instanceof ApiError
          ? (e.detail ?? `The request was refused (${e.status}).`)
          : "The search could not be run. Try again.",
      ),
  });
  const open = useMutation({
    mutationFn: (id: string) =>
      apiGet<S["RunOut"]>(`ai/opportunities/runs/${id}`),
    onSuccess: setShown,
  });

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Find candidates"
        info="Filtered by your eligibility, then scored on measured characteristics"
      >
        <form
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (amountOk) run.mutate();
          }}
        >
          <Field
            label="Check against a portfolio"
            hint="Optional: shows how a candidate would fit"
          >
            {(p) => (
              <select
                {...p}
                value={portfolioId}
                onChange={(e) => setPortfolioId(e.target.value)}
              >
                <option value="">None</option>
                {(portfolios.data ?? []).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field label="Asset class">
            {(p) => (
              <select
                {...p}
                value={assetClass}
                onChange={(e) => setAssetClass(e.target.value)}
              >
                <option value="">Any</option>
                {(classes.data ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <Field
            label={`Amount you have in mind (${currency}, optional)`}
            error={
              amountOk ? undefined : "Enter an amount with up to 2 decimals."
            }
          >
            {(p) => (
              <input
                {...p}
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            )}
          </Field>
          <Field label="How many">
            {(p) => (
              <select
                {...p}
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            )}
          </Field>
          <div className="sm:col-span-2 lg:col-span-4">
            <Button
              type="submit"
              variant="primary"
              disabled={run.isPending || !amountOk}
            >
              {run.isPending ? "Searching…" : "Find candidates"}
            </Button>
          </div>
        </form>
        {message ? (
          <p role="alert" className="mt-3 font-semibold text-negative-text">
            {message}
          </p>
        ) : null}
      </Card>
      {run.isPending ? <LoadingState label="Searching the universe" /> : null}
      {shown ? <RunView run={shown} /> : null}
      <Card title="Earlier searches">
        {runs.isPending ? (
          <LoadingState label="Loading earlier searches" lines={2} />
        ) : null}
        {runs.isError ? (
          <ErrorState
            message="Earlier searches could not be loaded."
            onRetry={() => void runs.refetch()}
          />
        ) : null}
        {runs.data && runs.data.length === 0 ? (
          <p className="text-fg-muted">No searches yet.</p>
        ) : null}
        {runs.data && runs.data.length > 0 ? (
          <ul className="flex flex-col gap-2">
            {runs.data.map((r) => (
              <li key={r.id}>
                <Button variant="ghost" onClick={() => open.mutate(r.id)}>
                  {r.created_at.slice(0, 16).replace("T", " ")} ·{" "}
                  {r.asset_class ?? "any class"} · explained by{" "}
                  {r.explanation_source}
                </Button>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>
    </div>
  );
}

function RunView({ run }: { run: S["RunOut"] }) {
  if (run.opportunities.length === 0) {
    return (
      <EmptyState title="No candidates">
        No instrument in the universe passed your eligibility rules for this
        search. Widen the asset class or review your investor profile.
      </EmptyState>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <ul className="grid gap-4 lg:grid-cols-2">
        {run.opportunities.map((o) => (
          <li key={o.asset_id}>
            <Card
              title={`${o.rank}. ${o.name}${o.symbol ? ` (${o.symbol})` : ""}`}
              as="article"
              actions={o.is_demo ? <DemoBadge /> : null}
            >
              <p className="text-fg-muted">
                {o.asset_class.replace(/_/g, " ")} · risk level {o.risk_level}{" "}
                of 5 · explained by{" "}
                {o.explanation_source === "model"
                  ? "the assistant, from the facts below"
                  : "a fixed template"}
              </p>
              <h3 className="mt-3 font-semibold">Why it surfaced</h3>
              <p>{o.explanation.why_surfaced}</p>
              <h3 className="mt-3 font-semibold">Thesis to test</h3>
              <p>{o.explanation.thesis}</p>
              <h3 className="mt-3 font-semibold">Risks</h3>
              <ul className="list-disc ps-5">
                {o.explanation.key_risks.map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
              <h3 className="mt-3 font-semibold">Assumptions</h3>
              <ul className="list-disc ps-5">
                {o.explanation.assumptions.map((a, i) => (
                  <li key={i}>{a}</li>
                ))}
              </ul>
              {o.actions?.length ? (
                <p className="mt-3 text-fg-muted">
                  Next steps for your research: {o.actions.join("; ")}.
                </p>
              ) : null}
              <p className="mt-3 text-[length:var(--ws-font-size-caption)] text-fg-muted">
                Evidence: {o.explanation.evidence_ids.length} item(s) from the
                research library. Not an order and not advice.
              </p>
            </Card>
          </li>
        ))}
      </ul>
      <DisclosurePanel
        title="About these results"
        notices={[run.notice ?? "Candidates are for research only."]}
      />
    </div>
  );
}

function Universe() {
  const [assetClass, setAssetClass] = useState("");
  const [eligibleOnly, setEligibleOnly] = useState(false);
  const classes = useQuery({
    queryKey: ["asset-classes"],
    queryFn: () => apiGet<S["AssetClassOut"][]>("asset-classes"),
    staleTime: 3_600_000,
  });
  const universe = useQuery({
    queryKey: ["universe", assetClass, eligibleOnly],
    queryFn: () =>
      apiGet<S["UniverseOut"]>(
        `universe?eligible_only=${eligibleOnly}${assetClass ? `&asset_class=${assetClass}` : ""}`,
      ),
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="min-w-48">
          <Field label="Asset class">
            {(p) => (
              <select
                {...p}
                value={assetClass}
                onChange={(e) => setAssetClass(e.target.value)}
              >
                <option value="">All</option>
                {(classes.data ?? []).map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        </div>
        <label className="flex min-h-9 items-center gap-2">
          <input
            type="checkbox"
            checked={eligibleOnly}
            onChange={(e) => setEligibleOnly(e.target.checked)}
          />
          Only instruments I am eligible for
        </label>
      </div>
      {universe.isPending ? (
        <LoadingState label="Loading the universe" />
      ) : null}
      {universe.isError ? (
        <ErrorState
          message="The universe could not be loaded."
          onRetry={() => void universe.refetch()}
        />
      ) : null}
      {universe.data ? (
        universe.data.items.length === 0 ? (
          <EmptyState title="Nothing matches">
            No instrument matches these filters.
          </EmptyState>
        ) : (
          <Card
            title={`${universe.data.eligible} of ${universe.data.total} eligible for you`}
            info={universe.data.jurisdiction_notice}
          >
            <DataGrid
              caption="Investment universe"
              rowKey="id"
              rows={universe.data.items.map((i) => ({
                id: i.asset_id,
                name: i.is_demo ? `${i.name} (DEMO)` : i.name,
                symbol: i.symbol ?? "",
                cls: i.asset_class.replace(/_/g, " "),
                risk: String(i.risk_level),
                liquidity: i.liquidity,
                minimum: i.minimum_investment
                  ? i.minimum_investment.amount
                  : "",
                currency: i.minimum_investment?.currency ?? i.currency,
                eligible: i.eligibility.eligible ? "Yes" : "No",
              }))}
              columns={[
                { key: "name", header: "Instrument" },
                { key: "symbol", header: "Symbol" },
                { key: "cls", header: "Class" },
                { key: "risk", header: "Risk (1-5)", align: "end" },
                { key: "liquidity", header: "Liquidity" },
                {
                  key: "minimum",
                  header: "Minimum",
                  kind: "money",
                  currencyKey: "currency",
                },
                { key: "eligible", header: "Eligible" },
              ]}
            />
            <div className="mt-3">
              <DisclosurePanel
                title="About the universe"
                notices={[universe.data.notice]}
              />
            </div>
          </Card>
        )
      ) : null}
    </div>
  );
}

function Research() {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const research = useQuery({
    queryKey: ["research", submitted],
    queryFn: () =>
      apiGet<S["ResearchOut"]>(
        `research?limit=20${submitted ? `&q=${encodeURIComponent(submitted)}` : ""}`,
      ),
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(query.trim());
        }}
      >
        <div className="min-w-64 flex-1">
          <Field label="Search the research library">
            {(p) => (
              <input
                {...p}
                maxLength={200}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            )}
          </Field>
        </div>
        <Button type="submit" variant="primary">
          Search
        </Button>
      </form>
      {research.isPending ? <LoadingState label="Searching" /> : null}
      {research.isError ? (
        <ErrorState
          message="Research could not be loaded."
          onRetry={() => void research.refetch()}
        />
      ) : null}
      {research.data && research.data.items.length === 0 ? (
        <EmptyState title="No research found">Try other words.</EmptyState>
      ) : null}
      {research.data && research.data.items.length > 0 ? (
        <>
          <ul className="flex flex-col gap-3">
            {research.data.items.map((e) => (
              <li key={e.id}>
                <Card
                  title={e.title}
                  as="article"
                  actions={
                    e.is_demo ? (
                      <DemoBadge />
                    ) : (
                      <DataAsOfLabel asOf={e.retrieved_at} />
                    )
                  }
                >
                  <p>{e.summary}</p>
                  <p className="mt-2 text-fg-muted">
                    {e.kind} · {e.source}
                    {e.symbol ? ` · ${e.symbol}` : ""} · published{" "}
                    {e.published_at.slice(0, 10)} · licence:{" "}
                    {e.licence_status.replace(/_/g, " ")}
                    {e.source_url ? ` · ${e.source_url}` : ""}
                  </p>
                </Card>
              </li>
            ))}
          </ul>
          <DisclosurePanel
            title="About the research library"
            notices={[research.data.notice]}
          />
        </>
      ) : null}
    </div>
  );
}
