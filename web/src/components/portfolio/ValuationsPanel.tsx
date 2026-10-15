"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiDelete, apiGet, apiPatch, apiPost, ApiError } from "@/lib/client/api";

import { Button } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { EmptyState, ErrorState, LoadingState } from "../states/states";
import { AssetPicker } from "./AssetPicker";

type Portfolio = components["schemas"]["PortfolioOut"];
type Valuation = components["schemas"]["ValuationOut"];

const DECIMAL = /^\d+(\.\d+)?$/;

/**
 * Manual valuations (P14-T08.4): the value you assert for an asset that has no market price (a
 * property, a private holding), on a date. Each is kept with its source and can be corrected or
 * removed; the portfolio's valuation uses the latest one on or before the date asked for.
 */
export function ValuationsPanel({ portfolio }: { portfolio: Portfolio }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Valuation | "new" | null>(null);
  const holdings = useQuery({
    queryKey: ["holdings", portfolio.id, "all"],
    queryFn: () => apiGet<components["schemas"]["HoldingOut"][]>(`portfolios/${portfolio.id}/holdings?include_closed=true`),
    staleTime: 60_000,
  });
  const valuations = useQuery({
    queryKey: ["valuations", portfolio.id],
    queryFn: () => apiGet<components["schemas"]["ValuationPage"]>(`portfolios/${portfolio.id}/valuations?limit=50`),
    staleTime: 30_000,
  });
  const remove = useMutation({
    mutationFn: (v: Valuation) => apiDelete(`portfolios/${portfolio.id}/valuations/${v.id}`),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  if (valuations.isPending) return <LoadingState label="Loading valuations" />;
  if (valuations.isError) return <ErrorState message="Valuations could not be loaded." onRetry={() => void valuations.refetch()} />;
  const names = new Map((holdings.data ?? []).map((h) => [h.asset.id, h.asset.name]));
  const items = valuations.data.items;
  const byId = new Map(items.map((v) => [v.id, v]));
  const rows = items.map((v) => ({ id: v.id, asset: names.get(v.asset_id) ?? "Asset", date: v.as_of, value: v.value.amount, currency: v.value.currency, source: v.source, note: v.note ?? "" }));
  return (
    <div className="flex flex-col gap-3">
      <div>
        <Button variant="primary" onClick={() => setEditing("new")}>
          Add a valuation
        </Button>
      </div>
      {rows.length ? (
        <DataGrid
          caption={`Valuations of ${portfolio.name}`}
          rowKey="id"
          rows={rows}
          columns={[
            { key: "asset", header: "Asset" },
            { key: "date", header: "As of", kind: "date" },
            { key: "value", header: "Value", kind: "money", currencyKey: "currency" },
            { key: "source", header: "Source" },
            { key: "note", header: "Note" },
            {
              key: "id",
              header: "Actions",
              render: (row) => {
                const v = byId.get(row.id);
                if (!v) return null;
                return (
                  <span className="flex gap-1">
                    <Button variant="ghost" onClick={() => setEditing(v)}>
                      Edit<span className="sr-only"> the valuation of {row.asset} on {row.date}</span>
                    </Button>
                    <Button variant="ghost" disabled={remove.isPending} onClick={() => remove.mutate(v)}>
                      Delete<span className="sr-only"> the valuation of {row.asset} on {row.date}</span>
                    </Button>
                  </span>
                );
              },
            },
          ]}
        />
      ) : (
        <EmptyState title="No valuations">Add one for an asset without a market price, such as a property.</EmptyState>
      )}
      {remove.isError ? <p role="alert" className="font-semibold text-negative-text">The valuation could not be deleted.</p> : null}
      <Drawer open={editing !== null} title={editing === "new" ? "Add a valuation" : "Edit the valuation"} onClose={() => setEditing(null)}>
        {editing ? <ValuationForm key={editing === "new" ? "new" : editing.id} portfolio={portfolio} names={names} existing={editing === "new" ? null : editing} onDone={() => setEditing(null)} /> : null}
      </Drawer>
    </div>
  );
}

function ValuationForm({ portfolio, names, existing, onDone }: { portfolio: Portfolio; names: Map<string, string>; existing: Valuation | null; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [assetId, setAssetId] = useState(existing?.asset_id ?? "");
  const [assetName, setAssetName] = useState(existing ? (names.get(existing.asset_id) ?? "") : "");
  const [amount, setAmount] = useState(existing?.value.amount ?? "");
  const [currency, setCurrency] = useState(existing?.value.currency ?? portfolio.base_currency);
  const [asOf, setAsOf] = useState((existing?.as_of ?? new Date().toISOString()).slice(0, 10));
  const [source, setSource] = useState(existing?.source ?? "owner estimate");
  const [note, setNote] = useState(existing?.note ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const problems = {
    asset: assetId ? undefined : "Choose the asset.",
    amount: DECIMAL.test(amount) ? undefined : "Enter the value.",
    source: source.trim() ? undefined : "Say where the value comes from.",
  };
  const save = useMutation({
    mutationFn: () => {
      const value = { amount, currency };
      return existing
        ? apiPatch(`portfolios/${portfolio.id}/valuations/${existing.id}`, { value, source: source.trim(), note: note.trim() || null })
        : apiPost(`portfolios/${portfolio.id}/valuations`, { asset_id: assetId, value, as_of: `${asOf}T00:00:00Z`, source: source.trim(), ...(note.trim() ? { note: note.trim() } : {}) });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      onDone();
    },
    onError: (e) => setMessage(e instanceof ApiError ? (e.detail ?? `The server refused the valuation (${e.status}).`) : "The valuation could not be saved."),
  });
  const [tried, setTried] = useState(false);
  return (
    <form
      noValidate
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        setTried(true);
        if (!problems.asset && !problems.amount && !problems.source) save.mutate();
      }}
    >
      {existing ? (
        <p>
          Asset: <strong>{assetName || "Asset"}</strong>
        </p>
      ) : (
        <AssetPicker value={assetId} selectedName={assetName} error={tried ? problems.asset : undefined} onChange={(a) => { setAssetId(a?.id ?? ""); setAssetName(a?.name ?? ""); }} />
      )}
      <Field label="Value" error={tried ? problems.amount : undefined}>{(p) => <input {...p} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />}</Field>
      <Field label="Currency" hint="Three-letter code.">{(p) => <input {...p} maxLength={3} value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} />}</Field>
      <Field label="As of" hint={existing ? "The date of a valuation cannot be changed; add a new one instead." : undefined}>{(p) => <input {...p} type="date" disabled={existing !== null} value={asOf} max={new Date().toISOString().slice(0, 10)} onChange={(e) => setAsOf(e.target.value)} />}</Field>
      <Field label="Source" error={tried ? problems.source : undefined} hint="For example an appraisal, a statement or your own estimate.">{(p) => <input {...p} maxLength={32} value={source} onChange={(e) => setSource(e.target.value)} />}</Field>
      <Field label="Note (optional)">{(p) => <input {...p} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      {message ? <p role="alert" className="font-semibold text-negative-text">{message}</p> : null}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>{existing ? "Save the changes" : "Add the valuation"}</Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
