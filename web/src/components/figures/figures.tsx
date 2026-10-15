import { absoluteOf, formatMoney, formatPercent, signOf, type Sign } from "@/lib/format/decimal";

import { Icon } from "../ui/Icon";

/**
 * Figures shown exactly as the API sends them (decimal strings, ADR-0003). Mirrors the mobile
 * `CurrencyAmount`, `ChangeIndicator`, `DataAsOfLabel`, `StaleChip`, `DemoBadge` and `RiskLabel`.
 */

type AmountSize = "display" | "headline" | "body";
const AMOUNT_SIZE: Record<AmountSize, string> = {
  display: "text-[length:var(--ws-font-size-display)] font-semibold leading-tight tracking-tight",
  headline: "text-[length:var(--ws-font-size-headline)] font-semibold leading-tight",
  body: "text-[length:var(--ws-font-size-body)] font-medium",
};

/** A money amount with tabular figures; the minor part is muted, as in the reference design. */
export function CurrencyAmount({
  value,
  currency,
  size = "body",
  locale,
}: {
  value: string;
  currency: string;
  size?: AmountSize;
  locale?: string;
}) {
  const parts = formatMoney(value, currency, locale);
  return (
    <span className={`tabular-nums ${AMOUNT_SIZE[size]}`}>
      <span className="sr-only">{parts.text}</span>
      <span aria-hidden="true">{parts.major}</span>
      {parts.minor ? (
        <span aria-hidden="true" className="text-fg-muted">
          {parts.minor}
        </span>
      ) : null}
    </span>
  );
}

const SIGN_STYLE: Record<Sign, { tone: string; icon: "arrowUp" | "arrowDown" | "minus"; word: string; symbol: string }> = {
  positive: { tone: "text-positive-text bg-positive/12", icon: "arrowUp", word: "up", symbol: "+" },
  negative: { tone: "text-negative-text bg-negative/12", icon: "arrowDown", word: "down", symbol: "−" },
  zero: { tone: "text-fg-muted bg-divider/60", icon: "minus", word: "unchanged", symbol: "" },
};

/**
 * A change shown with a sign, an arrow, text and colour, never colour alone (WCAG 1.4.1). Pass the
 * percentage and, optionally, the amount, both as decimal strings from the API.
 */
export function ChangeIndicator({
  percent,
  amount,
  currency,
  period,
}: {
  percent: string;
  amount?: string;
  currency?: string;
  period?: string;
}) {
  const sign = signOf(percent);
  const s = SIGN_STYLE[sign];
  const pct = formatPercent(absoluteOf(percent));
  const money = amount && currency ? formatMoney(absoluteOf(amount), currency).text : null;
  const spoken = `${s.word} ${pct}${money ? `, ${money}` : ""}${period ? ` ${period}` : ""}`;
  return (
    <span className="inline-flex flex-wrap items-center gap-2 text-[length:var(--ws-font-size-label)]">
      <span className="sr-only">{spoken}</span>
      <span aria-hidden="true" className={`inline-flex items-center gap-1 rounded-[var(--ws-radius-pill)] px-2 py-0.5 font-semibold ${s.tone}`}>
        <Icon name={s.icon} size={12} />
        {s.symbol}
        {pct}
      </span>
      {money ? (
        <span aria-hidden="true" className="text-fg-muted">
          {s.symbol}
          {money}
          {period ? ` ${period}` : ""}
        </span>
      ) : null}
    </span>
  );
}

/** "As of" time of a figure, as the server sent it (ISO 8601), shown in the user's locale. */
export function DataAsOfLabel({ asOf, locale = "en" }: { asOf: string; locale?: string }) {
  const date = new Date(asOf);
  const text = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(date);
  return (
    <span className="inline-flex items-center gap-1 text-[length:var(--ws-font-size-caption)] text-fg-muted">
      <Icon name="clock" size={12} />
      <span>
        As of <time dateTime={asOf}>{text}</time>
      </span>
    </span>
  );
}

function Badge({ children, tone, title }: { children: React.ReactNode; tone: string; title?: string }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-[var(--ws-radius-pill)] px-2 py-0.5 text-[length:var(--ws-font-size-caption)] font-semibold uppercase tracking-wide ${tone}`}
    >
      {children}
    </span>
  );
}

/** DEMO data is always labelled (CLAUDE.md). */
export function DemoBadge() {
  return (
    <Badge tone="bg-demo-badge text-on-demo-badge" title="Example data, not your accounts">
      Demo
    </Badge>
  );
}

/** Prices from the simulated provider are always labelled (P13, DEC-19). */
export function SimulatedBadge() {
  return (
    <Badge tone="bg-stale-banner text-on-stale-banner" title="Simulated data, not a live market">
      Simulated
    </Badge>
  );
}

/** Forecast probabilities that need calibration are labelled as not reliable (P13). */
export function CalibrationBadge() {
  return (
    <Badge tone="bg-stale-banner text-on-stale-banner" title="This probability requires calibration and is not reliable">
      Requires calibration
    </Badge>
  );
}

/** Stale data is never shown as current. */
export function StaleChip({ since }: { since?: string }) {
  return (
    <Badge tone="bg-stale-banner text-on-stale-banner" title={since ? `Last updated ${since}` : undefined}>
      <Icon name="alert" size={12} />
      Stale
    </Badge>
  );
}

const RISK = {
  low: { tone: "text-risk-low", label: "Low risk" },
  medium: { tone: "text-risk-medium", label: "Medium risk" },
  high: { tone: "text-risk-high", label: "High risk" },
} as const;

/** A risk level shown with an icon and a word, never colour alone. */
export function RiskLabel({ level }: { level: keyof typeof RISK }) {
  const r = RISK[level];
  return (
    <span className={`inline-flex items-center gap-1 text-[length:var(--ws-font-size-label)] font-semibold ${r.tone}`}>
      <Icon name="shield" size={14} />
      {r.label}
    </span>
  );
}
