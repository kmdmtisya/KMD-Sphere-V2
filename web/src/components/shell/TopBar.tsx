"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

import { apiGet, apiPatch } from "@/lib/client/api";
import { dataStatus } from "@/lib/client/data-status";
import { useStored } from "@/lib/client/local-storage";

import { IconButton } from "../controls/controls";
import { StaleChip } from "../figures/figures";
import { AppearanceSelector, ThemeCycleButton } from "../theme/appearance";
import { Icon } from "../ui/Icon";

type Portfolio = { id: string; name: string; archived_at: string | null };
type CurrencyPrefs = { reporting_currency: string };
type Currency = { code: string; name: string };
type FxStatus = { rates: { status: string }[] };
type AlertEvents = { items: { id: string }[] };

const FRESH = 60_000;
export const PORTFOLIO_KEY = "ws.portfolio";

const selectClass =
  "min-h-9 max-w-44 rounded-[var(--ws-radius-control)] border border-line bg-surface px-2 text-[length:var(--ws-font-size-label)] font-semibold text-fg";

function PortfolioSelect() {
  const portfolios = useQuery({ queryKey: ["portfolios"], queryFn: () => apiGet<Portfolio[]>("portfolios"), staleTime: FRESH });
  const [stored, setSelected] = useStored(PORTFOLIO_KEY);
  const selected = stored ?? "all";
  const active = (portfolios.data ?? []).filter((p) => !p.archived_at);
  return (
    <label className="flex items-center gap-2">
      <span className="sr-only">Portfolio</span>
      <select
        className={selectClass}
        value={active.some((p) => p.id === selected) ? selected : "all"}
        disabled={portfolios.isPending || portfolios.isError}
        onChange={(e) => setSelected(e.target.value)}
      >
        <option value="all">All portfolios</option>
        {active.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}

/** The reporting currency is a global account preference: changing it re-renders every figure. */
function CurrencySelect() {
  const queryClient = useQueryClient();
  const currencies = useQuery({ queryKey: ["currencies"], queryFn: () => apiGet<Currency[]>("currencies"), staleTime: 3_600_000 });
  const prefs = useQuery({ queryKey: ["currency-prefs"], queryFn: () => apiGet<CurrencyPrefs>("me/currency-preferences"), staleTime: FRESH });
  const change = useMutation({
    mutationFn: (code: string) => apiPatch<CurrencyPrefs>("me/currency-preferences", { reporting_currency: code }),
    onSuccess: async (data) => {
      queryClient.setQueryData(["currency-prefs"], data);
      // Every figure is shown in the reporting currency: refetch what depends on it.
      await queryClient.invalidateQueries({ predicate: (q) => !["currencies", "currency-prefs"].includes(String(q.queryKey[0])) });
    },
  });
  const current = prefs.data?.reporting_currency;
  return (
    <label className="flex items-center gap-2">
      <span className="sr-only">Reporting currency</span>
      <select
        className={selectClass}
        value={current ?? ""}
        disabled={!current || change.isPending}
        onChange={(e) => change.mutate(e.target.value)}
        aria-invalid={change.isError || undefined}
      >
        {!current ? <option value="">…</option> : null}
        {(currencies.data ?? [{ code: current ?? "", name: "" }]).map((c) => (
          <option key={c.code} value={c.code}>
            {c.code}
          </option>
        ))}
      </select>
    </label>
  );
}

function DataStatusChip() {
  const status = useQuery({ queryKey: ["fx-status"], queryFn: () => apiGet<FxStatus>("fx/status"), staleTime: FRESH, refetchInterval: () => (typeof document !== "undefined" && document.hidden ? false : FRESH) });
  const s = dataStatus(status.data?.rates);
  if (s.kind === "stale") return <StaleChip />;
  return (
    <span className="inline-flex items-center gap-1 text-[length:var(--ws-font-size-caption)] text-fg-muted" title="How fresh the exchange rates behind your figures are">
      <Icon name={s.kind === "current" ? "clock" : "alert"} size={12} />
      {s.label}
    </span>
  );
}

function Notifications() {
  const events = useQuery({ queryKey: ["alert-events"], queryFn: () => apiGet<AlertEvents>("alerts/events?unseen=true"), staleTime: FRESH });
  const count = events.data?.items.length ?? 0;
  return (
    <Link
      href="/alerts"
      aria-label={count ? `Notifications, ${count} unseen` : "Notifications"}
      className="relative inline-flex size-9 items-center justify-center rounded-[var(--ws-radius-control)] border border-divider text-fg-muted hover:bg-divider/60 hover:text-fg"
    >
      <Icon name="alert" size={16} />
      {count ? (
        <span aria-hidden="true" className="absolute -end-1 -top-1 min-w-4 rounded-full bg-primary px-1 text-center text-[length:var(--ws-font-size-caption)] font-semibold text-on-primary">
          {count > 9 ? "9+" : count}
        </span>
      ) : null}
    </Link>
  );
}

function ProfileMenu({ name, email }: { name: string; email?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const menuId = useId();
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  const csrf = typeof document === "undefined" ? "" : decodeURIComponent(/(?:^|; )__Host-ws_csrf=([^;]+)/.exec(document.cookie)?.[1] ?? "");
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={`Account menu for ${name}`}
        aria-expanded={open}
        aria-controls={menuId}
        aria-haspopup="true"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex min-h-9 items-center gap-2 rounded-[var(--ws-radius-control)] border border-divider px-2 font-semibold"
      >
        <span aria-hidden="true" className="inline-flex size-6 items-center justify-center rounded-full bg-primary text-[length:var(--ws-font-size-caption)] text-on-primary">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="hidden max-w-32 truncate md:inline">{name}</span>
      </button>
      {open ? (
        <div id={menuId} role="group" aria-label="Profile" className="absolute end-0 top-11 z-50 flex w-72 flex-col gap-3 rounded-[var(--ws-radius-card)] border border-divider bg-surface-elevated p-4 shadow-lg">
          <div>
            <p className="font-semibold">{name}</p>
            {email ? <p className="text-[length:var(--ws-font-size-caption)] text-fg-muted">{email}</p> : null}
          </div>
          <AppearanceSelector />
          <Link href="/settings" onClick={() => setOpen(false)} className="font-semibold text-primary underline">
            Settings and security
          </Link>
          <form method="post" action="/api/auth/logout">
            <input type="hidden" name="csrf" value={csrf} />
            <button type="submit" className="inline-flex min-h-9 w-full items-center justify-center rounded-[var(--ws-radius-control)] border border-line font-semibold">
              Sign out
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}

export function TopBar({
  user,
  showMenu,
  onMenu,
  onPanel,
  panelOpen,
}: {
  user: { name: string; email?: string };
  showMenu: boolean;
  onMenu: () => void;
  onPanel: () => void;
  panelOpen: boolean;
}) {
  return (
    <header className="flex flex-wrap items-center gap-2 border-b border-divider bg-surface px-3 py-2">
      {showMenu ? <IconButton icon="table" label="Open the menu" onClick={onMenu} /> : null}
      <Link href="/home" className="me-2 font-semibold">
        WealthSphere
      </Link>
      <button
        type="button"
        disabled
        title="Search across your portfolios, assets and goals arrives with the dashboard (P14-T07)"
        className="hidden min-h-9 min-w-48 items-center gap-2 rounded-[var(--ws-radius-control)] border border-divider px-3 text-fg-muted opacity-70 lg:inline-flex"
      >
        <Icon name="sort" size={14} />
        <span className="flex-1 text-start">Search</span>
        <kbd className="text-[length:var(--ws-font-size-caption)]">Ctrl K</kbd>
      </button>
      <div className="ms-auto flex flex-wrap items-center gap-2">
        <PortfolioSelect />
        <CurrencySelect />
        <DataStatusChip />
        <Notifications />
        <ThemeCycleButton />
        <IconButton icon="info" label={panelOpen ? "Close the Copilot panel" : "Open the Copilot panel"} aria-pressed={panelOpen} onClick={onPanel} />
        <ProfileMenu name={user.name} email={user.email} />
      </div>
    </header>
  );
}
