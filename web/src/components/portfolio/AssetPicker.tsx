"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";

import { Button } from "../controls/controls";
import { Field } from "../controls/forms";

type Asset = components["schemas"]["AssetOut"];
type Summary = components["schemas"]["AssetSummary"];

const CURRENCY = /^[A-Z]{3}$/;

/** Search the catalogue and your own assets, or create a custom asset (P14-T08.4). */
export function AssetPicker({
  label = "Asset",
  value,
  selectedName,
  onChange,
  error,
}: {
  label?: string;
  value: string;
  selectedName?: string;
  onChange: (asset: { id: string; name: string } | null) => void;
  error?: string;
}) {
  const [text, setText] = useState("");
  const [term, setTerm] = useState("");
  const [creating, setCreating] = useState(false);
  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), 250);
    return () => clearTimeout(id);
  }, [text]);
  const results = useQuery({
    queryKey: ["asset-search", term],
    queryFn: () => apiGet<components["schemas"]["AssetSearchResult"]>(`assets/search?q=${encodeURIComponent(term)}&limit=8`),
    enabled: term.length >= 2,
    staleTime: 30_000,
  });
  const items: Summary[] = results.data?.items ?? [];
  return (
    <div className="flex flex-col gap-2">
      <Field label={label} error={error} hint={value ? `Selected: ${selectedName ?? value}` : "Type at least two letters of its name or symbol."}>
        {(p) => <input {...p} type="search" value={text} onChange={(e) => setText(e.target.value)} placeholder="Search assets" autoComplete="off" />}
      </Field>
      {term.length >= 2 ? (
        <ul aria-label="Matching assets" className="flex flex-col gap-1">
          {items.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                aria-pressed={a.id === value}
                onClick={() => onChange({ id: a.id, name: a.name })}
                className="flex w-full items-center justify-between gap-2 rounded-[var(--ws-radius-control)] border border-divider px-3 py-2 text-start hover:bg-divider/60 aria-pressed:border-primary"
              >
                <span className="font-medium">{a.name}</span>
                <span className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
                  {[a.symbol, a.currency, a.is_custom ? "your asset" : null].filter(Boolean).join(" · ")}
                </span>
              </button>
            </li>
          ))}
          {!results.isFetching && !items.length ? <li className="text-fg-muted">No assets match.</li> : null}
        </ul>
      ) : null}
      {value ? (
        <Button variant="ghost" onClick={() => onChange(null)}>
          Clear the asset
        </Button>
      ) : null}
      <Button onClick={() => setCreating((v) => !v)} aria-expanded={creating}>
        {creating ? "Cancel the custom asset" : "Create a custom asset"}
      </Button>
      {creating ? (
        <CustomAsset
          onCreated={(a) => {
            setCreating(false);
            onChange({ id: a.id, name: a.name });
          }}
        />
      ) : null}
    </div>
  );
}

function CustomAsset({ onCreated }: { onCreated: (asset: Asset) => void }) {
  const queryClient = useQueryClient();
  const classes = useQuery({ queryKey: ["asset-classes"], queryFn: () => apiGet<components["schemas"]["AssetClassOut"][]>("asset-classes"), staleTime: 3_600_000 });
  const [form, setForm] = useState({ asset_class: "", name: "", currency: "USD", symbol: "" });
  const [message, setMessage] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      apiPost<Asset>("assets", {
        asset_class: form.asset_class,
        name: form.name.trim(),
        currency: form.currency,
        ...(form.symbol.trim() ? { symbol: form.symbol.trim() } : {}),
        metadata: {},
      }),
    onSuccess: async (asset) => {
      await queryClient.invalidateQueries({ queryKey: ["asset-search"] });
      onCreated(asset);
    },
    onError: (e) => setMessage(e instanceof ApiError ? (e.detail ?? "The asset could not be created.") : "The asset could not be created."),
  });
  const ready = form.asset_class !== "" && form.name.trim() !== "" && CURRENCY.test(form.currency);
  return (
    <fieldset className="flex flex-col gap-3 rounded-[var(--ws-radius-control)] border border-divider p-3">
      <legend className="px-1 font-semibold">New custom asset</legend>
      <Field label="Asset class">
        {(p) => (
          <select {...p} value={form.asset_class} onChange={(e) => setForm({ ...form, asset_class: e.target.value })}>
            <option value="">Choose a class</option>
            {(classes.data ?? []).map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Name">{(p) => <input {...p} value={form.name} maxLength={200} onChange={(e) => setForm({ ...form, name: e.target.value })} />}</Field>
      <Field label="Currency" hint="Three-letter code, for example USD.">
        {(p) => <input {...p} value={form.currency} maxLength={3} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} />}
      </Field>
      <Field label="Symbol (optional)">{(p) => <input {...p} value={form.symbol} maxLength={32} onChange={(e) => setForm({ ...form, symbol: e.target.value })} />}</Field>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      <Button variant="primary" disabled={!ready || create.isPending} onClick={() => create.mutate()}>
        Create the asset
      </Button>
    </fieldset>
  );
}
