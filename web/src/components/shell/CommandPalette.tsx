"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import type { components } from "@/lib/api";
import { apiGet } from "@/lib/client/api";
import type { NavGroup } from "@/lib/nav/nav";

import { Icon } from "../ui/Icon";

type Hit = components["schemas"]["SearchHit"];
type Entry = { key: string; label: string; hint: string; href: string };

/** Where each kind of record opens until its detail pages exist (P14-T08, T10, T11). */
const KIND_HREF: Record<Hit["kind"], string> = {
  portfolio: "/portfolio",
  goal: "/goals",
  liability: "/planning/net-worth",
  asset: "/portfolio",
};
const KIND_LABEL: Record<Hit["kind"], string> = { portfolio: "Portfolio", goal: "Goal", liability: "Liability", asset: "Asset" };

/**
 * Search and command palette (P14-T07.3, Ctrl/⌘+K): jump to any page of the portal, and find your own
 * portfolios, goals, liabilities and assets (`GET /api/v1/search`, owner-scoped on the server). It uses
 * the native modal dialog, so focus is trapped and Esc closes it.
 */
export function CommandPalette({ open, onClose, groups }: { open: boolean; onClose: () => void; groups: NavGroup[] }) {
  const dialog = useRef<HTMLDialogElement | null>(null);
  const router = useRouter();
  const listId = useId();
  const [text, setText] = useState("");
  const [debounced, setDebounced] = useState("");
  const [active, setActive] = useState(0);

  useEffect(() => {
    const el = dialog.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(text.trim()), 200);
    return () => clearTimeout(id);
  }, [text]);

  const search = useQuery({
    queryKey: ["search", debounced],
    queryFn: () => apiGet<components["schemas"]["SearchOut"]>(`search?q=${encodeURIComponent(debounced)}`),
    enabled: open && debounced.length >= 2,
    staleTime: 30_000,
  });

  const needle = text.trim().toLowerCase();
  const pages: Entry[] = groups
    .flatMap((g) => g.items.map((i) => ({ key: `page:${i.href}`, label: i.label, hint: `Go to · ${g.label}`, href: i.href })))
    .filter((e) => !needle || e.label.toLowerCase().includes(needle) || e.hint.toLowerCase().includes(needle))
    .slice(0, 8);
  const records: Entry[] = (debounced.length >= 2 && needle ? (search.data?.results ?? []) : []).map((h) => ({
    key: `${h.kind}:${h.id}`,
    label: h.title,
    hint: `${KIND_LABEL[h.kind]}${h.subtitle ? ` · ${h.subtitle}` : ""}`,
    href: KIND_HREF[h.kind],
  }));
  const entries = [...records, ...pages];
  const current = Math.min(active, Math.max(0, entries.length - 1));

  function choose(entry: Entry | undefined) {
    if (!entry) return;
    onClose();
    router.push(entry.href);
  }

  const status = search.isFetching
    ? "Searching your records…"
    : search.isError
      ? "Search is unavailable right now; pages still work."
      : entries.length
        ? `${entries.length} result${entries.length === 1 ? "" : "s"}. Enter to open, Esc to close.`
        : "No results.";

  return (
    <dialog
      ref={dialog}
      aria-label="Search and commands"
      onClose={() => {
        setText("");
        setDebounced("");
        setActive(0);
        onClose();
      }}
      onClick={(e) => {
        if (e.target === dialog.current) onClose();
      }}
      className="m-auto mt-24 w-[min(40rem,calc(100vw-2rem))] rounded-[var(--ws-radius-card)] border border-divider bg-surface-elevated p-0 text-fg shadow-lg backdrop:bg-fg/40"
    >
      <div className="flex items-center gap-2 border-b border-divider px-3">
        <Icon name="sort" size={16} />
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={entries[current] ? `${listId}-${current}` : undefined}
          aria-label="Search your portfolios, goals and assets, or jump to a page"
          placeholder="Search or jump to…"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActive(Math.min(entries.length - 1, current + 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive(Math.max(0, current - 1));
            } else if (e.key === "Enter") {
              e.preventDefault();
              choose(entries[current]);
            }
          }}
          className="min-h-12 flex-1 bg-transparent outline-none"
        />
      </div>
      <ul id={listId} role="listbox" aria-label="Results" className="max-h-80 overflow-y-auto p-1">
        {entries.map((e, i) => (
          <li
            key={e.key}
            id={`${listId}-${i}`}
            role="option"
            aria-selected={i === current}
            onMouseMove={() => setActive(i)}
            onClick={() => choose(e)}
            className={`flex cursor-pointer items-center justify-between gap-3 rounded-[var(--ws-radius-control)] px-3 py-2 ${i === current ? "bg-primary text-on-primary" : ""}`}
          >
            <span className="font-medium">{e.label}</span>
            <span className={`text-[length:var(--ws-font-size-caption)] ${i === current ? "" : "text-fg-muted"}`}>{e.hint}</span>
          </li>
        ))}
      </ul>
      <p role="status" className="border-t border-divider px-3 py-2 text-[length:var(--ws-font-size-caption)] text-fg-muted">
        {status}
      </p>
    </dialog>
  );
}
