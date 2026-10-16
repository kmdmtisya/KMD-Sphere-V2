"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import type { components } from "@/lib/api";
import { apiGet, apiPost, ApiError } from "@/lib/client/api";
import {
  emptyOrder,
  orderRequest,
  validateOrder,
  type OrderValues,
} from "@/lib/forex/forms";

import { Card } from "../cards/cards";
import { Button, SegmentedControl } from "../controls/controls";
import { Field } from "../controls/forms";
import { DataGrid } from "../data/DataGrid";
import {
  DisclosurePanel,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBanner,
} from "../states/states";

type S = components["schemas"];
type Account = S["ForexPaperAccountOut"];

/** Always shown on this panel, and on every card in it. */
export function PaperBadge() {
  return (
    <span className="inline-flex items-center rounded-[var(--ws-radius-pill)] border-2 border-fg px-2 py-0.5 text-[length:var(--ws-font-size-caption)] font-bold uppercase tracking-wide">
      Paper trading · simulated money
    </span>
  );
}

const errorText = (e: unknown, fallback: string) =>
  e instanceof ApiError ? (e.detail ?? `${fallback} (${e.status}).`) : fallback;

/**
 * Paper trading (P14-T24.4): practice orders against recorded prices with fictional money. It is a
 * simulation: there is no real broker, no real order and no real money, and paper results never
 * appear in your wealth figures. Every number here is the backend's.
 */
export function Paper() {
  const queryClient = useQueryClient();
  const accounts = useQuery({
    queryKey: ["paper-accounts"],
    queryFn: () => apiGet<S["ForexPaperAccountsOut"]>("forex/paper/accounts"),
    staleTime: 15_000,
  });
  const [chosen, setChosen] = useState<string | null>(null);
  const [name, setName] = useState("My practice account");
  const [message, setMessage] = useState<string | null>(null);
  const prefs = useQuery({
    queryKey: ["currency-preferences"],
    queryFn: () =>
      apiGet<{ reporting_currency: string }>("me/currency-preferences"),
    staleTime: 60_000,
  });
  const create = useMutation({
    mutationFn: () =>
      apiPost<Account>("forex/paper/accounts", {
        name: name.trim(),
        currency: prefs.data?.reporting_currency ?? "USD",
      }),
    onMutate: () => setMessage(null),
    onSuccess: async (a) => {
      setChosen(a.id);
      await queryClient.invalidateQueries({ queryKey: ["paper-accounts"] });
    },
    onError: (e) =>
      setMessage(errorText(e, "The account could not be created")),
  });
  if (accounts.isPending)
    return <LoadingState label="Loading paper accounts" reserve="12rem" />;
  if (accounts.isError)
    return (
      <ErrorState
        message="Paper accounts could not be loaded."
        onRetry={() => void accounts.refetch()}
      />
    );
  const list = accounts.data.items.filter((a) => a.status === "active");
  const account = list.find((a) => a.id === chosen) ?? list[0];
  return (
    <div className="flex flex-col gap-4">
      <StatusBanner kind="info">
        <PaperBadge />{" "}
        <span className="ms-2">
          Practice with fictional money. Nothing here is a real order, and these
          results are never part of your net worth or portfolio figures.
        </span>
      </StatusBanner>
      {!account ? (
        <Card title="Open a paper account" actions={<PaperBadge />}>
          <EmptyState title="No paper account yet">
            A paper account starts with fictional money so you can try ideas
            without risk.
          </EmptyState>
          <form
            className="mt-2 flex flex-wrap items-end gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              if (name.trim()) create.mutate();
            }}
          >
            <div className="min-w-64 flex-1">
              <Field label="Account name">
                {(p) => (
                  <input
                    {...p}
                    maxLength={60}
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                )}
              </Field>
            </div>
            <Button
              type="submit"
              variant="primary"
              disabled={create.isPending || !name.trim()}
            >
              {create.isPending ? "Opening…" : "Open a paper account"}
            </Button>
          </form>
          {message ? (
            <p role="alert" className="mt-3 font-semibold text-negative-text">
              {message}
            </p>
          ) : null}
        </Card>
      ) : (
        <>
          {list.length > 1 ? (
            <div className="max-w-xs">
              <Field label="Paper account">
                {(p) => (
                  <select
                    {...p}
                    value={account.id}
                    onChange={(e) => setChosen(e.target.value)}
                  >
                    {list.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                )}
              </Field>
            </div>
          ) : null}
          <AccountSummary account={account} />
          <OrderForm key={`o-${account.id}`} account={account} />
          <Positions key={`p-${account.id}`} account={account} />
          <Orders key={`r-${account.id}`} account={account} />
          <Journal key={`j-${account.id}`} account={account} />
          <DisclosurePanel
            title="About paper trading"
            notices={[account.notice]}
          />
        </>
      )}
    </div>
  );
}

function AccountSummary({ account: a }: { account: Account }) {
  return (
    <Card title={a.name} actions={<PaperBadge />} as="article">
      {a.warnings.length ? (
        <div className="mb-3">
          <StatusBanner kind="stale">{a.warnings.join(" ")}</StatusBanner>
        </div>
      ) : null}
      <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Balance (fictional)"
          value={`${a.balance} ${a.currency}`}
        />
        <Stat label="Equity" value={`${a.equity} ${a.currency}`} />
        <Stat
          label="Open profit or loss"
          value={`${a.unrealised_pnl} ${a.currency}`}
        />
        <Stat label="Margin used" value={`${a.used_margin} ${a.currency}`} />
        <Stat label="Free margin" value={`${a.free_margin} ${a.currency}`} />
        <Stat
          label="Realised today"
          value={`${a.realised_today} ${a.currency}`}
        />
        <Stat
          label="Realised this week"
          value={`${a.realised_this_week} ${a.currency}`}
        />
        <Stat
          label="Open positions, pending orders"
          value={`${a.open_positions}, ${a.pending_orders}`}
        />
      </dl>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {label}
      </dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function OrderForm({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const instruments = useQuery({
    queryKey: ["forex-instruments"],
    queryFn: () => apiGet<S["InstrumentsOut"]>("forex/instruments"),
    staleTime: 300_000,
  });
  const [values, setValues] = useState<OrderValues>(emptyOrder);
  const [problems, setProblems] = useState<ReturnType<typeof validateOrder>>(
    {},
  );
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(
    null,
  );
  const set = <K extends keyof OrderValues>(key: K, value: OrderValues[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
  const place = useMutation({
    mutationFn: () =>
      apiPost<S["ForexPaperOrderPlacedOut"]>(
        `forex/paper/accounts/${account.id}/orders`,
        orderRequest(values),
      ),
    onMutate: () => setMessage(null),
    onSuccess: async (out) => {
      setMessage({
        ok: true,
        text: out.position
          ? `Paper order filled at ${out.position.entry_price}. ${out.warnings.join(" ")}`
          : `Paper order ${out.order.status}. ${out.warnings.join(" ")}`,
      });
      await queryClient.invalidateQueries({ queryKey: ["paper-accounts"] });
      await queryClient.invalidateQueries({
        queryKey: ["paper-positions", account.id],
      });
      await queryClient.invalidateQueries({
        queryKey: ["paper-orders", account.id],
      });
    },
    onError: (e) =>
      setMessage({
        ok: false,
        text: errorText(e, "The paper order was refused"),
      }),
  });
  const text = (key: keyof OrderValues, labelText: string, hint?: string) => (
    <Field label={labelText} error={problems[key]} hint={hint}>
      {(p) => (
        <input
          {...p}
          inputMode="decimal"
          value={values[key]}
          onChange={(e) => set(key, e.target.value as never)}
        />
      )}
    </Field>
  );
  return (
    <Card
      title="Place a paper order"
      actions={<PaperBadge />}
      info="A simulated market order filled at the latest recorded price, with the spread. It is not sent to any broker"
    >
      <form
        noValidate
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => {
          e.preventDefault();
          const found = validateOrder(values);
          setProblems(found);
          if (Object.keys(found).length === 0) place.mutate();
        }}
      >
        <Field label="Pair">
          {(p) => (
            <select
              {...p}
              value={values.instrument}
              onChange={(e) => set("instrument", e.target.value)}
            >
              {(
                instruments.data?.items ?? [
                  { code: values.instrument, base: "EUR", quote: "USD" },
                ]
              ).map((i) => (
                <option key={i.code} value={i.code}>
                  {i.base}/{i.quote}
                </option>
              ))}
            </select>
          )}
        </Field>
        <SegmentedControl
          label="Side"
          options={
            [
              { value: "long", label: "Buy (long)" },
              { value: "short", label: "Sell (short)" },
            ] as const
          }
          value={values.side}
          onChange={(s) => set("side", s)}
        />
        {text("lots", "Size in lots")}
        {text("stop", "Stop price", "Required: every paper order has a stop")}
        {text("target", "Target price (optional)")}
        <Field label="Strategy tag (optional)" error={problems.tag}>
          {(p) => (
            <input
              {...p}
              maxLength={40}
              value={values.tag}
              onChange={(e) => set("tag", e.target.value)}
            />
          )}
        </Field>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-3">
          <Button type="submit" variant="primary" disabled={place.isPending}>
            {place.isPending ? "Placing…" : "Place paper order"}
          </Button>
          {message ? (
            <p
              role={message.ok ? "status" : "alert"}
              className={
                message.ok
                  ? "text-fg-muted"
                  : "font-semibold text-negative-text"
              }
            >
              {message.text}
            </p>
          ) : null}
        </div>
      </form>
    </Card>
  );
}

function Positions({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const positions = useQuery({
    queryKey: ["paper-positions", account.id],
    queryFn: () =>
      apiGet<S["ForexPaperPositionsOut"]>(
        `forex/paper/accounts/${account.id}/positions`,
      ),
    staleTime: 10_000,
  });
  const close = useMutation({
    mutationFn: (id: string) =>
      apiPost<S["ForexPaperPositionOut"]>(
        `forex/paper/accounts/${account.id}/positions/${id}/close`,
        {},
      ),
    onMutate: () => setMessage(null),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["paper-positions", account.id],
      });
      await queryClient.invalidateQueries({ queryKey: ["paper-accounts"] });
    },
    onError: (e) =>
      setMessage(errorText(e, "The position could not be closed")),
  });
  return (
    <Card title="Paper positions" actions={<PaperBadge />}>
      {positions.isPending ? (
        <LoadingState label="Loading positions" lines={2} />
      ) : null}
      {positions.isError ? (
        <ErrorState
          message="Positions could not be loaded."
          onRetry={() => void positions.refetch()}
        />
      ) : null}
      {message ? (
        <p role="alert" className="mb-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {positions.data && positions.data.items.length === 0 ? (
        <p className="text-fg-muted">No paper positions yet.</p>
      ) : null}
      {positions.data && positions.data.items.length > 0 ? (
        <DataGrid
          caption="Paper positions"
          rowKey="id"
          rows={positions.data.items.map((p) => ({
            id: p.id,
            pair: p.instrument.replace("_", "/"),
            side: p.side === "long" ? "Long" : "Short",
            lots: p.lots,
            entry: p.entry_price,
            now: p.current_price ?? p.exit_price ?? "",
            pnl:
              p.status === "open"
                ? (p.unrealised_pnl ?? "")
                : (p.realised_pnl ?? ""),
            status:
              p.status === "open"
                ? "Open"
                : `Closed (${p.exit_reason ?? "manual"})`,
            kind: p.data_type.replace(/_/g, " "),
            open: p.status === "open" ? "yes" : "",
          }))}
          columns={[
            { key: "pair", header: "Pair" },
            { key: "side", header: "Side" },
            { key: "lots", header: "Lots", align: "end" },
            { key: "entry", header: "Entry", align: "end" },
            { key: "now", header: "Price", align: "end" },
            { key: "pnl", header: "Profit or loss", align: "end" },
            { key: "status", header: "Status" },
            { key: "kind", header: "Price data" },
            {
              key: "id",
              header: "Actions",
              render: (r) =>
                r.open ? (
                  <Button
                    variant="ghost"
                    disabled={close.isPending}
                    onClick={() => close.mutate(r.id)}
                  >
                    Close
                    <span className="sr-only">
                      {" "}
                      the paper {r.pair} position
                    </span>
                  </Button>
                ) : null,
            },
          ]}
        />
      ) : null}
    </Card>
  );
}

function Orders({ account }: { account: Account }) {
  const orders = useQuery({
    queryKey: ["paper-orders", account.id],
    queryFn: () =>
      apiGet<S["ForexPaperOrdersOut"]>(
        `forex/paper/accounts/${account.id}/orders`,
      ),
    staleTime: 10_000,
  });
  return (
    <Card title="Paper orders" actions={<PaperBadge />}>
      {orders.isPending ? (
        <LoadingState label="Loading orders" lines={2} />
      ) : null}
      {orders.isError ? (
        <ErrorState
          message="Orders could not be loaded."
          onRetry={() => void orders.refetch()}
        />
      ) : null}
      {orders.data && orders.data.items.length === 0 ? (
        <p className="text-fg-muted">No paper orders yet.</p>
      ) : null}
      {orders.data && orders.data.items.length > 0 ? (
        <DataGrid
          caption="Paper orders"
          rowKey="id"
          rows={orders.data.items.map((o) => ({
            id: o.id,
            when: o.created_at.slice(0, 16).replace("T", " "),
            pair: o.instrument.replace("_", "/"),
            side: o.side === "long" ? "Buy" : "Sell",
            lots: o.lots,
            stop: o.stop,
            target: o.target ?? "",
            status: o.status,
            tag: o.strategy_tag ?? "",
          }))}
          columns={[
            { key: "when", header: "Placed" },
            { key: "pair", header: "Pair" },
            { key: "side", header: "Side" },
            { key: "lots", header: "Lots", align: "end" },
            { key: "stop", header: "Stop", align: "end" },
            { key: "target", header: "Target", align: "end" },
            { key: "status", header: "Status" },
            { key: "tag", header: "Tag" },
          ]}
        />
      ) : null}
    </Card>
  );
}

function Journal({ account }: { account: Account }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const [tags, setTags] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const journal = useQuery({
    queryKey: ["paper-journal", account.id],
    queryFn: () =>
      apiGet<S["ForexPaperJournalListOut"]>(
        `forex/paper/accounts/${account.id}/journal`,
      ),
    staleTime: 15_000,
  });
  const add = useMutation({
    mutationFn: () =>
      apiPost(`forex/paper/accounts/${account.id}/journal`, {
        note: note.trim(),
        tags: tags
          .split(",")
          .map((t) => t.trim())
          .filter(Boolean)
          .slice(0, 10),
      }),
    onMutate: () => setMessage(null),
    onSuccess: async () => {
      setNote("");
      setTags("");
      await queryClient.invalidateQueries({
        queryKey: ["paper-journal", account.id],
      });
    },
    onError: (e) => setMessage(errorText(e, "The note could not be saved")),
  });
  return (
    <Card
      title="Trading journal"
      actions={<PaperBadge />}
      info="Notes on your practice trades: what you expected and what you learned"
    >
      <form
        className="mb-4 grid gap-3 sm:grid-cols-[1fr_14rem_auto] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          if (note.trim()) add.mutate();
        }}
      >
        <Field label="Note">
          {(p) => (
            <input
              {...p}
              maxLength={2000}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </Field>
        <Field label="Tags (comma separated)">
          {(p) => (
            <input
              {...p}
              value={tags}
              onChange={(e) => setTags(e.target.value)}
            />
          )}
        </Field>
        <Button type="submit" disabled={add.isPending || !note.trim()}>
          Add the note
        </Button>
      </form>
      {message ? (
        <p role="alert" className="mb-3 font-semibold text-negative-text">
          {message}
        </p>
      ) : null}
      {journal.isPending ? (
        <LoadingState label="Loading the journal" lines={2} />
      ) : null}
      {journal.isError ? (
        <ErrorState
          message="The journal could not be loaded."
          onRetry={() => void journal.refetch()}
        />
      ) : null}
      {journal.data && journal.data.items.length === 0 ? (
        <p className="text-fg-muted">No notes yet.</p>
      ) : null}
      {journal.data && journal.data.items.length > 0 ? (
        <ul className="flex flex-col gap-3">
          {journal.data.items.map((j) => (
            <li
              key={j.id}
              className="rounded-[var(--ws-radius-control)] border border-divider p-3"
            >
              <p>{j.note}</p>
              <p className="text-fg-muted">
                {j.created_at.slice(0, 16).replace("T", " ")}
                {j.tags.length ? ` · ${j.tags.join(", ")}` : ""}
              </p>
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
