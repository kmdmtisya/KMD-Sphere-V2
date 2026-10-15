"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPatch, apiPost, ApiError } from "@/lib/client/api";

import { Button } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { EmptyState, ErrorState, LoadingState } from "../states/states";

type Portfolio = components["schemas"]["PortfolioOut"];
type PortfolioType = Portfolio["portfolio_type"];
export const PORTFOLIO_TYPES: PortfolioType[] = ["personal", "family", "retirement", "geographic", "strategy"];
const label = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

/** Portfolios (P14-T08.1): list, create. Editing and archiving are on the portfolio's own page. */
export function PortfolioList() {
  const [showArchived, setShowArchived] = useState(false);
  const [creating, setCreating] = useState(false);
  const portfolios = useQuery({
    queryKey: ["portfolios", { archived: showArchived }],
    queryFn: () => apiGet<Portfolio[]>(`portfolios?include_archived=${showArchived}`),
    staleTime: 30_000,
  });
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">Portfolios</h1>
          <p className="text-fg-muted">Your portfolios, holdings and valuations. Each keeps its own ledger in its own currency.</p>
        </div>
        <div className="flex gap-2">
          <Button aria-pressed={showArchived} onClick={() => setShowArchived((v) => !v)}>
            {showArchived ? "Hide archived" : "Show archived"}
          </Button>
          <Button variant="primary" icon="arrowUp" onClick={() => setCreating(true)}>
            New portfolio
          </Button>
        </div>
      </header>
      {portfolios.isPending ? <LoadingState label="Loading portfolios" /> : null}
      {portfolios.isError ? <ErrorState message="Portfolios could not be loaded." onRetry={() => void portfolios.refetch()} /> : null}
      {portfolios.data ? (
        portfolios.data.length ? (
          <DataGrid
            caption="Portfolios"
            rowKey="id"
            rows={portfolios.data.map((p) => ({ id: p.id, name: p.name, type: label(p.portfolio_type), currency: p.base_currency, created: p.created_at, status: p.archived_at ? "Archived" : "Active" }))}
            columns={[
              { key: "name", header: "Portfolio", render: (row) => <Link href={`/portfolio/${row.id}`} className="font-semibold text-primary underline">{row.name}</Link> },
              { key: "type", header: "Type" },
              { key: "currency", header: "Currency" },
              { key: "created", header: "Created", kind: "date" },
              { key: "status", header: "Status" },
            ]}
          />
        ) : (
          <EmptyState title="No portfolios yet" action={<Button variant="primary" onClick={() => setCreating(true)}>Create your first portfolio</Button>}>
            A portfolio holds a ledger of transactions in one currency.
          </EmptyState>
        )
      ) : null}
      <Drawer open={creating} title="New portfolio" onClose={() => setCreating(false)}>
        {creating ? <PortfolioForm onDone={() => setCreating(false)} /> : null}
      </Drawer>
    </div>
  );
}

/** Create (no `existing`) or edit a portfolio. The currency is fixed once it exists. */
export function PortfolioForm({ existing, onDone }: { existing?: Portfolio; onDone: () => void }) {
  const queryClient = useQueryClient();
  const currencies = useQuery({ queryKey: ["currencies"], queryFn: () => apiGet<components["schemas"]["CurrencyOut"][]>("currencies"), staleTime: 3_600_000 });
  const reporting = useQuery({ queryKey: ["currency-prefs"], queryFn: () => apiGet<{ reporting_currency: string }>("me/currency-preferences"), staleTime: 60_000, enabled: !existing });
  const [name, setName] = useState(existing?.name ?? "");
  const [currency, setCurrency] = useState(existing?.base_currency ?? "");
  const [type, setType] = useState<PortfolioType>(existing?.portfolio_type ?? "personal");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [tried, setTried] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const chosenCurrency = currency || reporting.data?.reporting_currency || "USD";
  const problem = name.trim() ? undefined : "Give the portfolio a name.";
  const save = useMutation({
    mutationFn: () =>
      existing
        ? apiPatch<Portfolio>(`portfolios/${existing.id}`, { name: name.trim(), portfolio_type: type, description: description.trim() || null })
        : apiPost<Portfolio>("portfolios", { name: name.trim(), base_currency: chosenCurrency, portfolio_type: type, ...(description.trim() ? { description: description.trim() } : {}) }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      onDone();
    },
    onError: (e) => setMessage(e instanceof ApiError ? (e.status === 409 ? "You already have a portfolio with this name." : (e.detail ?? "The portfolio could not be saved.")) : "The portfolio could not be saved."),
  });
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        setTried(true);
        setMessage(null);
        if (!problem) save.mutate();
      }}
    >
      <Field label="Name" error={tried ? problem : undefined}>{(p) => <input {...p} maxLength={100} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
      <Field label="Currency" hint={existing ? "A portfolio's currency cannot be changed: its postings are converted into it." : "Fixed once the portfolio exists. Defaults to your reporting currency."}>
        {(p) => (
          <select {...p} disabled={Boolean(existing)} value={chosenCurrency} onChange={(e) => setCurrency(e.target.value)}>
            {(currencies.data ?? [{ code: chosenCurrency, name: "" }]).map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
          </select>
        )}
      </Field>
      <Field label="Type">
        {(p) => (
          <select {...p} value={type} onChange={(e) => setType(e.target.value as PortfolioType)}>
            {PORTFOLIO_TYPES.map((t) => <option key={t} value={t}>{label(t)}</option>)}
          </select>
        )}
      </Field>
      <Field label="Description (optional)">{(p) => <input {...p} maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} />}</Field>
      {message ? <p role="alert" className="font-semibold text-negative-text">{message}</p> : null}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>{existing ? "Save the changes" : "Create the portfolio"}</Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
