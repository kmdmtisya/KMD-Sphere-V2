import { formatMoney, formatPercent } from "@/lib/format/decimal";

/**
 * Allocation as a segmented bar with a list underneath (reference image 1, "Distribution"). The
 * percentages and amounts are the API's decimal strings: segment widths use the percentage string
 * directly as a CSS width, so nothing is calculated here. Each list row repeats the series colour
 * with a marker and the name, so colour is never the only signal.
 */
export type DistributionItem = { label: string; percent: string; amount: string };

const MARKERS = ["●", "■", "▲", "◆", "▼", "★"];

export function DistributionBar({ items, currency, label }: { items: DistributionItem[]; currency: string; label: string }) {
  return (
    <div className="flex flex-col gap-4">
      <div aria-hidden="true" className="flex h-3 w-full gap-1 overflow-hidden rounded-[var(--ws-radius-pill)]">
        {items.map((item, i) => (
          <span
            key={item.label}
            className="h-full rounded-[var(--ws-radius-pill)]"
            style={{ width: `${item.percent}%`, background: `var(--ws-series${(i % 6) + 1})` }}
          />
        ))}
      </div>
      <ul aria-label={label} className="flex flex-col divide-y divide-divider">
        {items.map((item, i) => (
          <li key={item.label} className="flex items-center justify-between gap-3 py-2.5">
            <span className="flex items-center gap-2">
              <span aria-hidden="true" style={{ color: `var(--ws-series${(i % 6) + 1})` }}>
                {MARKERS[i % MARKERS.length]}
              </span>
              <span className="flex flex-col">
                <span className="font-medium">{item.label}</span>
                <span className="text-[length:var(--ws-font-size-caption)] text-fg-muted">{formatPercent(item.percent)}</span>
              </span>
            </span>
            <span className="tabular-nums font-medium">{formatMoney(item.amount, currency).text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
