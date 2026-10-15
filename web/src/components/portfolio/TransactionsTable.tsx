"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import { TYPE_RULES, TYPES, type TransactionType } from "@/lib/portfolio/transaction-form";

import { Button } from "../controls/controls";
import { Drawer, Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import { EmptyState, ErrorState, LoadingState } from "../states/states";

type Portfolio = components["schemas"]["PortfolioOut"];
type Transaction = components["schemas"]["TransactionOut"];
type Page = components["schemas"]["TransactionPage"];

const PAGE = 25;

/**
 * The ledger (P14-T08.3): newest first, filterable by type, loaded a page at a time. The ledger is
 * append-only, so there is no edit or delete: a mistake is undone with a reversal that is itself a
 * ledger entry, and both stay visible.
 */
export function TransactionsTable({ portfolio }: { portfolio: Portfolio }) {
  const [type, setType] = useState<"" | TransactionType>("");
  const [reversing, setReversing] = useState<Transaction | null>(null);
  const holdings = useQuery({
    queryKey: ["holdings", portfolio.id, "all"],
    queryFn: () => apiGet<components["schemas"]["HoldingOut"][]>(`portfolios/${portfolio.id}/holdings?include_closed=true`),
    staleTime: 60_000,
  });
  const ledger = useInfiniteQuery({
    queryKey: ["transactions", portfolio.id, type],
    initialPageParam: "",
    queryFn: ({ pageParam }) =>
      apiGet<Page>(`portfolios/${portfolio.id}/transactions?limit=${PAGE}${type ? `&transaction_type=${type}` : ""}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 30_000,
  });

  if (ledger.isPending) return <LoadingState label="Loading the ledger" />;
  if (ledger.isError) return <ErrorState message="The ledger could not be loaded." onRetry={() => void ledger.refetch()} />;

  const names = new Map((holdings.data ?? []).map((h) => [h.asset.id, h.asset.name]));
  const all = ledger.data.pages.flatMap((p) => p.items);
  const byId = new Map(all.map((t) => [t.id, t]));
  const rows = all.map((t) => ({
    id: t.id,
    date: t.trade_date,
    type: TYPE_RULES[t.transaction_type as TransactionType]?.label ?? t.transaction_type,
    asset: t.asset_id ? (names.get(t.asset_id) ?? "Asset") : "Cash",
    amount: t.gross_amount.amount,
    currency: t.gross_amount.currency,
    status: t.reversed_by_transaction_id ? "Reversed" : t.reverses_transaction_id ? "Reversal" : "",
    note: t.note ?? "",
  }));

  return (
    <div className="flex flex-col gap-3">
      <div className="max-w-xs">
        <Field label="Show">
          {(p) => (
            <select {...p} value={type} onChange={(e) => setType(e.target.value as "" | TransactionType)}>
              <option value="">All transaction types</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_RULES[t].label}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
      {rows.length ? (
        <DataGrid
          caption={`Transactions of ${portfolio.name}`}
          rowKey="id"
          rows={rows}
          columns={[
            { key: "date", header: "Date", kind: "date" },
            { key: "type", header: "Type" },
            { key: "asset", header: "Asset" },
            { key: "amount", header: "Amount", kind: "money", currencyKey: "currency" },
            { key: "status", header: "Status" },
            { key: "note", header: "Note" },
            {
              key: "id",
              header: "Actions",
              render: (row) => {
                const t = byId.get(row.id);
                if (!t || row.status) return null;
                return (
                  <Button variant="ghost" onClick={() => setReversing(t)}>
                    Reverse<span className="sr-only"> the {row.type.toLowerCase()} of {row.date}</span>
                  </Button>
                );
              },
            },
          ]}
        />
      ) : (
        <EmptyState title="No transactions">{type ? "Nothing of this type yet." : "Add a deposit or a buy to start this ledger."}</EmptyState>
      )}
      {ledger.hasNextPage ? (
        <div>
          <Button onClick={() => void ledger.fetchNextPage()} disabled={ledger.isFetchingNextPage}>
            {ledger.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      ) : null}
      <ReverseDrawer portfolio={portfolio} transaction={reversing} onClose={() => setReversing(null)} />
    </div>
  );
}

function ReverseDrawer({ portfolio, transaction, onClose }: { portfolio: Portfolio; transaction: Transaction | null; onClose: () => void }) {
  return (
    <Drawer open={transaction !== null} title="Reverse a transaction" onClose={onClose}>
      {transaction ? <ReverseForm key={transaction.id} portfolio={portfolio} transaction={transaction} onClose={onClose} /> : null}
    </Drawer>
  );
}

function ReverseForm({ portfolio, transaction, onClose }: { portfolio: Portfolio; transaction: Transaction; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState<string | null>(null);
  const reverse = useMutation({
    mutationFn: () => apiPost(`portfolios/${portfolio.id}/transactions/${transaction.id}/reversal`, note.trim() ? { note: note.trim() } : {}, { idempotencyKey: key }),
    onSuccess: async () => {
      await queryClient.invalidateQueries();
      onClose();
    },
    onError: (e) => setMessage(e instanceof ApiError ? (e.detail ?? `The server refused the reversal (${e.status}).`) : "The reversal could not be sent. Try again; it will not be posted twice."),
  });
  return (
    <div className="flex flex-col gap-4">
      <p>
        This adds a new entry that cancels the {TYPE_RULES[transaction.transaction_type as TransactionType]?.label.toLowerCase()} of {transaction.trade_date}. The original stays in the ledger,
        marked as reversed, so your history is complete.
      </p>
      <Field label="Reason (optional)">{(p) => <input {...p} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
      {message ? (
        <p role="alert" className="font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button variant="primary" disabled={reverse.isPending} onClick={() => reverse.mutate()}>
          {reverse.isPending ? "Reversing…" : "Reverse the transaction"}
        </Button>
        <Button onClick={onClose}>Keep it</Button>
      </div>
    </div>
  );
}
