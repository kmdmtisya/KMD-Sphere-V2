"use client";

import { useCallback } from "react";

import { plotNumber } from "@/lib/chart/plot-values";
import { formatMoney, formatPercent } from "@/lib/format/decimal";

import { ChartFrame } from "./ChartFrame";
import type { DistributionItem } from "./DistributionBar";
import { DistributionBar } from "./DistributionBar";
import { EChart } from "./EChart";
import type { ChartTheme } from "./useChartTheme";

/**
 * Allocation (asset class, currency or country) as a donut beside the distribution list, which
 * names every slice with its marker, percentage and amount. Mirrors the mobile
 * `AllocationDonutChart`. Shares come from the API; they are converted only to draw the slices.
 */
export function AllocationDonutChart({
  title,
  info,
  items,
  currency,
  summary,
}: {
  title: string;
  info?: string;
  items: DistributionItem[];
  currency: string;
  summary: string;
}) {
  const build = useCallback(
    (theme: ChartTheme) => ({
      tooltip: {
        trigger: "item" as const,
        backgroundColor: theme.tooltipSurface,
        borderWidth: 0,
        textStyle: { color: theme.onTooltip },
        formatter: (param: unknown) => {
          const i = (param as { dataIndex?: number }).dataIndex ?? 0;
          const item = items[i];
          return item ? `${item.label}<br/><b>${formatPercent(item.percent)}</b> · ${formatMoney(item.amount, currency).text}` : "";
        },
      },
      series: [
        {
          type: "pie" as const,
          radius: ["58%", "82%"],
          padAngle: 2,
          itemStyle: { borderRadius: 4, borderColor: theme.surface, borderWidth: 2 },
          label: { show: false },
          data: items.map((item, i) => ({
            name: item.label,
            value: plotNumber(item.percent),
            itemStyle: { color: theme.series[i % theme.series.length] },
          })),
        },
      ],
    }),
    [items, currency],
  );

  return (
    <ChartFrame
      title={title}
      info={info}
      summary={summary}
      columns={["Category", "Share", `Amount (${currency})`]}
      rows={items.map((item) => ({ label: item.label, values: [formatPercent(item.percent), formatMoney(item.amount, currency).text] }))}
      legend={<DistributionBar items={items} currency={currency} label={`${title} breakdown`} />}
    >
      <EChart build={build} height={180} />
    </ChartFrame>
  );
}
