import { Icon, type IconName } from "../ui/Icon";

/**
 * Loading, empty, error and status states (mirrors the mobile `SkeletonLoader`, `EmptyState`,
 * `ErrorState`, `StatusBanner` and `DisclosurePanel`). Every async view uses them, so no page is ever
 * blank or silently stale.
 */

/** A placeholder block while data loads; announced once by the surrounding region. */
export function Skeleton({ className = "h-4 w-full" }: { className?: string }) {
  return <span aria-hidden="true" className={`block animate-pulse rounded-md bg-divider ${className}`} />;
}

/**
 * A loading region: skeleton lines plus a polite status message for screen readers. `reserve` is
 * the height (a CSS length such as "26rem") the content will take, kept while loading so the page
 * does not jump when the data arrives (Cumulative Layout Shift, QG-31.2).
 */
export function LoadingState({ label = "Loading", lines = 3, reserve }: { label?: string; lines?: number; reserve?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex flex-col gap-2" style={reserve ? { minHeight: reserve } : undefined}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={i === 0 ? "h-8 w-1/2" : "h-4 w-full"} />
      ))}
    </div>
  );
}

function StateFrame({
  icon,
  title,
  children,
  action,
  role,
}: {
  icon: IconName;
  title: string;
  children?: React.ReactNode;
  action?: React.ReactNode;
  role?: "alert" | "status";
}) {
  return (
    <div role={role} className="flex flex-col items-center gap-3 px-4 py-8 text-center">
      <span className="text-fg-muted">
        <Icon name={icon} size={28} />
      </span>
      <p className="text-[length:var(--ws-font-size-title)] font-semibold">{title}</p>
      {children ? <div className="max-w-md text-fg-muted">{children}</div> : null}
      {action}
    </div>
  );
}

export function EmptyState({ title, children, action }: { title: string; children?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <StateFrame icon="inbox" title={title} action={action}>
      {children}
    </StateFrame>
  );
}

/** An error with the server's correlation id (for support) and a retry action. */
export function ErrorState({
  title = "Something went wrong",
  message,
  correlationId,
  onRetry,
}: {
  title?: string;
  message?: string;
  correlationId?: string;
  onRetry?: () => void;
}) {
  return (
    <StateFrame
      icon="alert"
      title={title}
      role="alert"
      action={
        onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="inline-flex min-h-9 items-center gap-2 rounded-[var(--ws-radius-control)] border border-line px-3 font-semibold"
          >
            <Icon name="refresh" size={14} />
            Try again
          </button>
        ) : null
      }
    >
      {message ? <p>{message}</p> : null}
      {correlationId ? (
        <p className="mt-1 text-[length:var(--ws-font-size-caption)]">
          Reference: <code>{correlationId}</code>
        </p>
      ) : null}
    </StateFrame>
  );
}

const BANNER = {
  info: { tone: "border-line bg-surface-elevated text-fg", icon: "info" as const },
  warning: { tone: "border-warning bg-stale-banner text-on-stale-banner", icon: "alert" as const },
  stale: { tone: "border-warning bg-stale-banner text-on-stale-banner", icon: "clock" as const },
};

/** A page-level message (stale data, offline, information). */
export function StatusBanner({ kind = "info", children }: { kind?: keyof typeof BANNER; children: React.ReactNode }) {
  const b = BANNER[kind];
  return (
    <div role={kind === "info" ? "status" : "alert"} className={`flex items-start gap-2 rounded-[var(--ws-radius-control)] border px-3 py-2 ${b.tone}`}>
      <span className="mt-0.5">
        <Icon name={b.icon} size={16} />
      </span>
      <div>{children}</div>
    </div>
  );
}

/**
 * The server's notices (not advice, DEMO, simulated, assumptions) shown exactly as sent, never
 * shortened away (WEB_UI_UX_SPECIFICATION.md §1). Collapsible, open by default.
 */
export function DisclosurePanel({ title = "About these figures", notices }: { title?: string; notices: string[] }) {
  return (
    <details open className="rounded-[var(--ws-radius-control)] border border-divider bg-surface-elevated px-3 py-2 text-[length:var(--ws-font-size-caption)] text-fg-muted">
      <summary className="cursor-pointer font-semibold text-fg">{title}</summary>
      <ul className="mt-2 list-disc space-y-1 ps-5">
        {notices.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    </details>
  );
}
