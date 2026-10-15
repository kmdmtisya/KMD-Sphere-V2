"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import { emptyForm, TYPE_RULES, TYPES, toRequest, validate, type FormValues } from "@/lib/portfolio/transaction-form";

import { Button } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { AssetPicker } from "./AssetPicker";

type Portfolio = components["schemas"]["PortfolioOut"];

/**
 * Add a transaction (P14-T08.3): every type, in the posting's own currency with the FX rate when it
 * differs from the portfolio's, as on mobile. The ledger is append-only: a mistake is fixed with a
 * reversal, never an edit. A new Idempotency-Key per opened form makes a retry after a network
 * failure safe (the server returns the original posting instead of a second one).
 */
export function TransactionDrawer({ portfolio, open, onClose }: { portfolio: Portfolio; open: boolean; onClose: () => void }) {
  return (
    <Drawer open={open} title={`Add a transaction to ${portfolio.name}`} onClose={onClose}>
      {open ? <TransactionForm portfolio={portfolio} onDone={onClose} /> : null}
    </Drawer>
  );
}

function TransactionForm({ portfolio, onDone }: { portfolio: Portfolio; onDone: () => void }) {
  const queryClient = useQueryClient();
  const [values, setValues] = useState<FormValues>(() => emptyForm(portfolio.base_currency, new Date().toISOString().slice(0, 10)));
  const [assetName, setAssetName] = useState("");
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [problems, setProblems] = useState<ReturnType<typeof validate>>({});
  const [message, setMessage] = useState<string | null>(null);
  const currencies = useQuery({ queryKey: ["currencies"], queryFn: () => apiGet<components["schemas"]["CurrencyOut"][]>("currencies"), staleTime: 3_600_000 });
  const rules = TYPE_RULES[values.type];
  const set = <K extends keyof FormValues>(key: K, value: FormValues[K]) => setValues((v) => ({ ...v, [key]: value }));

  const save = useMutation({
    mutationFn: () => apiPost(`portfolios/${portfolio.id}/transactions`, toRequest(values, portfolio.base_currency), { idempotencyKey }),
    onSuccess: async () => {
      // Everything derived from the ledger is refetched; the server recalculated it.
      await queryClient.invalidateQueries();
      onDone();
    },
    onError: (e) => setMessage(e instanceof ApiError ? (e.detail ?? `The server refused the transaction (${e.status}).`) : "The transaction could not be sent. Try again; it will not be posted twice."),
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = validate(values, portfolio.base_currency);
    setProblems(found);
    setMessage(null);
    if (Object.keys(found).length === 0) save.mutate();
  }

  return (
    <form onSubmit={submit} noValidate className="flex flex-col gap-4">
      <Field label="Type" hint={rules.help}>
        {(p) => (
          <select {...p} value={values.type} onChange={(e) => set("type", e.target.value as FormValues["type"])}>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {TYPE_RULES[t].label}
              </option>
            ))}
          </select>
        )}
      </Field>
      <Field label="Trade date" error={problems.tradeDate}>
        {(p) => <input {...p} type="date" value={values.tradeDate} max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("tradeDate", e.target.value)} />}
      </Field>
      {rules.asset !== "none" ? (
        <AssetPicker
          label={rules.asset === "optional" ? "Asset (optional)" : "Asset"}
          value={values.assetId}
          selectedName={assetName}
          error={problems.assetId}
          onChange={(a) => {
            set("assetId", a?.id ?? "");
            setAssetName(a?.name ?? "");
          }}
        />
      ) : null}
      <Field label="Currency of this posting" error={problems.currency} hint={`The portfolio is in ${portfolio.base_currency}.`}>
        {(p) => (
          <select {...p} value={values.currency} onChange={(e) => set("currency", e.target.value)}>
            {(currencies.data ?? [{ code: portfolio.base_currency, name: "" }]).map((c) => (
              <option key={c.code} value={c.code}>
                {c.code}
              </option>
            ))}
          </select>
        )}
      </Field>
      {values.currency !== portfolio.base_currency ? (
        <Field label={`Exchange rate to ${portfolio.base_currency}`} error={problems.fxRate} hint={`1 ${values.currency} = how many ${portfolio.base_currency}. The rate you enter is stored with the posting.`}>
          {(p) => <input {...p} inputMode="decimal" value={values.fxRate} onChange={(e) => set("fxRate", e.target.value)} />}
        </Field>
      ) : null}
      {rules.quantity !== "none" ? (
        <Field label="Quantity" error={problems.quantity}>
          {(p) => <input {...p} inputMode="decimal" value={values.quantity} onChange={(e) => set("quantity", e.target.value)} />}
        </Field>
      ) : null}
      {rules.unitPrice !== "none" ? (
        <Field label={rules.unitPrice === "optional" ? "Price per unit (optional)" : "Price per unit"} error={problems.unitPrice}>
          {(p) => <input {...p} inputMode="decimal" value={values.unitPrice} onChange={(e) => set("unitPrice", e.target.value)} />}
        </Field>
      ) : null}
      {rules.gross !== "none" ? (
        <Field
          label={rules.gross === "optional" ? "Total amount (optional)" : "Amount"}
          error={problems.gross}
          hint={rules.gross === "optional" ? "Leave blank and the server works it out from quantity and price." : values.type === "VALUATION_ADJUSTMENT" ? "May be negative." : undefined}
        >
          {(p) => <input {...p} inputMode="decimal" value={values.gross} onChange={(e) => set("gross", e.target.value)} />}
        </Field>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Fees (optional)" error={problems.fees}>
          {(p) => <input {...p} inputMode="decimal" value={values.fees} onChange={(e) => set("fees", e.target.value)} />}
        </Field>
        <Field label="Taxes (optional)" error={problems.taxes}>
          {(p) => <input {...p} inputMode="decimal" value={values.taxes} onChange={(e) => set("taxes", e.target.value)} />}
        </Field>
      </div>
      <Field label="Note (optional)">{(p) => <input {...p} maxLength={500} value={values.note} onChange={(e) => set("note", e.target.value)} />}</Field>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" variant="primary" disabled={save.isPending}>
          {save.isPending ? "Adding…" : "Add the transaction"}
        </Button>
        <Button onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}
