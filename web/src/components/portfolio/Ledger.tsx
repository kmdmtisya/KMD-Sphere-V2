"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";
import { useStored } from "@/lib/client/local-storage";

import { Button } from "../controls/controls";
import { Field } from "../controls/forms";
import { EmptyState, ErrorState, LoadingState } from "../states/states";
import { PORTFOLIO_KEY } from "../shell/TopBar";
import { TransactionDrawer } from "./TransactionDrawer";
import { TransactionsTable } from "./TransactionsTable";

type Portfolio = components["schemas"]["PortfolioOut"];

/** The transactions page (P14-T08.3): the ledger of one portfolio, starting from the one chosen in the top bar. */
export function Ledger() {
  const [stored] = useStored(PORTFOLIO_KEY);
  const [choice, setChoice] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const portfolios = useQuery({ queryKey: ["portfolios", { archived: false }], queryFn: () => apiGet<Portfolio[]>("portfolios?include_archived=false"), staleTime: 30_000 });
  if (portfolios.isPending) return <LoadingState label="Loading portfolios" />;
  if (portfolios.isError) return <ErrorState message="Portfolios could not be loaded." onRetry={() => void portfolios.refetch()} />;
  const list = portfolios.data;
  if (!list.length) {
    return (
      <EmptyState title="No portfolios yet" action={<Link href="/portfolio" className="font-semibold text-primary underline">Create a portfolio</Link>}>
        Transactions live in a portfolio&apos;s ledger.
      </EmptyState>
    );
  }
  const selectedId = [choice, stored].find((id) => id && list.some((p) => p.id === id)) ?? list[0].id;
  const portfolio = list.find((p) => p.id === selectedId) ?? list[0];
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[length:var(--ws-font-size-headline)] font-semibold">Transactions</h1>
          <p className="text-fg-muted">The ledger is append-only: a mistake is fixed with a reversal, never an edit.</p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-48">
            <Field label="Portfolio">
              {(p) => (
                <select {...p} value={portfolio.id} onChange={(e) => setChoice(e.target.value)}>
                  {list.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </select>
              )}
            </Field>
          </div>
          <Button variant="primary" icon="arrowUp" onClick={() => setAdding(true)}>
            Add a transaction
          </Button>
        </div>
      </header>
      <TransactionsTable key={portfolio.id} portfolio={portfolio} />
      <TransactionDrawer portfolio={portfolio} open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}
