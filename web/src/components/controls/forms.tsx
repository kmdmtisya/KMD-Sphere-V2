"use client";

import { useEffect, useId, useRef } from "react";

import { IconButton } from "./controls";

/** Form building blocks (P14-T08): a labelled field with its hint and error, and a side drawer. */
const input =
  "min-h-9 w-full rounded-[var(--ws-radius-control)] border border-line bg-surface px-3 text-fg aria-[invalid=true]:border-negative disabled:opacity-60";

export function Field({
  label,
  error,
  hint,
  children,
}: {
  label: string;
  error?: string;
  hint?: string;
  children: (props: { id: string; "aria-invalid"?: boolean; "aria-describedby"?: string; className: string }) => React.ReactNode;
}) {
  const id = useId();
  const describedBy = [hint ? `${id}-hint` : null, error ? `${id}-error` : null].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[length:var(--ws-font-size-label)] font-semibold">
        {label}
      </label>
      {children({ id, "aria-invalid": error ? true : undefined, "aria-describedby": describedBy, className: input })}
      {hint ? (
        <p id={`${id}-hint`} className="text-[length:var(--ws-font-size-caption)] text-fg-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${id}-error`} className="text-[length:var(--ws-font-size-caption)] font-semibold text-negative-text">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/**
 * A panel that slides in from the end, on the native modal dialog: focus is trapped, Esc closes it
 * and focus returns to where it was.
 */
export function Drawer({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDialogElement | null>(null);
  const titleId = useId();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      className="m-0 ms-auto h-dvh max-h-dvh w-full max-w-lg overflow-y-auto rounded-none border-s border-divider bg-surface-elevated p-0 text-fg shadow-lg backdrop:bg-fg/40"
    >
      {open ? (
        <div className="flex flex-col gap-4 p-5">
          <div className="flex items-center justify-between gap-2">
            <h2 id={titleId} className="text-[length:var(--ws-font-size-headline)] font-semibold">
              {title}
            </h2>
            <IconButton icon="expand" label="Close" onClick={onClose} />
          </div>
          {children}
        </div>
      ) : null}
    </dialog>
  );
}
