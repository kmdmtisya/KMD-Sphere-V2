"use client";

import { useId, useState } from "react";

import { Card } from "../cards/cards";
import { IconButton } from "../controls/controls";

/**
 * Every chart sits in a frame with a text summary and a "view as table" alternative (WCAG 1.1.1,
 * WEB_UI_UX_SPECIFICATION.md §7). The chart itself is decorative for assistive technology; the
 * summary and the table carry the information. Mirrors the mobile `ChartFrame`.
 */
export type ChartTableRow = { label: string; values: string[] };

export function ChartFrame({
  title,
  info,
  summary,
  columns,
  rows,
  actions,
  legend,
  children,
}: {
  title: string;
  info?: string;
  /** One sentence stating what the chart shows, in words (from figures the API sent). */
  summary: string;
  /** Column headers of the table alternative; the first column is the row label. */
  columns: string[];
  rows: ChartTableRow[];
  actions?: React.ReactNode;
  /** Readable content shown beside the chart (for example the allocation list); not hidden. */
  legend?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [asTable, setAsTable] = useState(false);
  const summaryId = useId();
  return (
    <Card
      title={title}
      info={info}
      actions={
        <>
          {actions}
          <IconButton
            icon={asTable ? "chart" : "table"}
            label={asTable ? `Show ${title} as a chart` : `Show ${title} as a table`}
            aria-pressed={asTable}
            onClick={() => setAsTable((v) => !v)}
          />
        </>
      }
    >
      <p id={summaryId} className="sr-only">
        {summary}
      </p>
      {asTable ? (
        <div className="overflow-x-auto">
          <table className="w-full text-start text-[length:var(--ws-font-size-label)]" aria-describedby={summaryId}>
            <caption className="sr-only">{title}</caption>
            <thead>
              <tr className="border-b border-divider text-fg-muted">
                {columns.map((c, i) => (
                  <th key={c} scope="col" className={`py-2 font-semibold ${i === 0 ? "text-start" : "text-end"}`}>
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.label} className="border-b border-divider last:border-0">
                  <th scope="row" className="py-2 text-start font-medium">
                    {r.label}
                  </th>
                  {r.values.map((v, i) => (
                    <td key={i} className="py-2 text-end tabular-nums">
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : legend ? (
        <div className="grid items-center gap-4 sm:grid-cols-[minmax(0,180px)_1fr]">
          <div aria-hidden="true">{children}</div>
          {legend}
        </div>
      ) : (
        <div aria-hidden="true">{children}</div>
      )}
    </Card>
  );
}
