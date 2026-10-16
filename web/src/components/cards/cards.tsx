import { useId } from "react";

import { CurrencyAmount, ChangeIndicator } from "../figures/figures";
import { Icon } from "../ui/Icon";

/**
 * Card anatomy from the reference design (docs/web/WEB_DESIGN_REFERENCE_ANALYSIS.md §2): a raised
 * surface with a 1 px border and the card radius; a title bar with an optional info hint on the left
 * and compact actions on the right. Mirrors the mobile `WealthCard`.
 */
export function Card({
  title,
  info,
  actions,
  children,
  className = "",
  as: Tag = "section",
}: {
  title?: string;
  info?: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  as?: "section" | "article" | "div";
}) {
  const id = useId();
  const headingId = title ? `${id}-title` : undefined;
  return (
    <Tag
      aria-labelledby={headingId}
      className={`rounded-[var(--ws-radius-card)] border border-divider bg-surface p-5 text-fg ${className}`}
    >
      {title || actions ? (
        <header className="mb-4 flex min-h-8 flex-wrap items-center justify-between gap-3">
          {title ? (
            <h2 id={headingId} className="flex items-center gap-1.5 text-[length:var(--ws-font-size-label)] font-semibold text-fg-muted">
              {title}
              {info ? (
                <span title={info} className="inline-flex text-fg-muted">
                  <Icon name="info" size={14} label={info} />
                </span>
              ) : null}
            </h2>
          ) : (
            <span />
          )}
          {actions ? <div className="flex min-w-0 max-w-full flex-wrap items-center gap-1">{actions}</div> : null}
        </header>
      ) : null}
      {children}
    </Tag>
  );
}

/**
 * A KPI: label, a large amount with the muted minor part, and the change pill followed by the
 * period delta (reference image 1, "Total Assets"). Every value is a decimal string from the API.
 */
export function KpiCard({
  label,
  info,
  value,
  currency,
  changePercent,
  changeAmount,
  period,
  footer,
}: {
  label: string;
  info?: string;
  value: string;
  currency: string;
  changePercent?: string;
  changeAmount?: string;
  period?: string;
  footer?: React.ReactNode;
}) {
  return (
    <Card title={label} info={info} as="article">
      <div className="flex flex-col gap-2">
        <CurrencyAmount value={value} currency={currency} size="display" />
        {changePercent ? (
          <ChangeIndicator percent={changePercent} amount={changeAmount} currency={currency} period={period} />
        ) : null}
        {footer ? <div className="mt-2">{footer}</div> : null}
      </div>
    </Card>
  );
}
