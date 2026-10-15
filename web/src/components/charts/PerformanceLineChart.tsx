"use client";

import { useCallback, useMemo } from "react";

import { plotNumber } from "@/lib/chart/plot-values";
import { formatMoney } from "@/lib/format/decimal";

import { ChartFrame } from "./ChartFrame";
import { EChart } from "./EChart";
import type { ChartTheme } from "./useChartTheme";

/**
 * A value over time (wealth, portfolio value, net worth) as an area line, with the reference
 * design's chart chrome: muted grid, crosshair and a tooltip card. Mirrors the mobile
 * `PerformanceLineChart`. Points are the API's decimal strings; the tooltip and the table show them
 * exactly, and they are converted only to place the line (src/lib/chart/plot-values.ts).
 */
export type ValuePoint = { date: string; value: string };

export function PerformanceLineChart({
  title,
  info,
  points,
  currency,
  summary,
  locale = "en",
  actions,
  height = 260,
}: {
  title: string;
  info?: string;
  points: ValuePoint[];
  currency: string;
  summary: string;
  locale?: string;
  actions?: React.ReactNode;
  height?: number;
}) {
  const dateLabel = useMemo(() => new Intl.DateTimeFormat(locale, { day: "numeric", month: "short" }), [locale]);
  const axisLabel = useMemo(
    () => new Intl.NumberFormat(locale, { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }),
    [locale, currency],
  );

  const build = useCallback(
    (theme: ChartTheme) => {
      const line = theme.series[0];
      return {
        grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
        tooltip: {
          trigger: "axis" as const,
          backgroundColor: theme.tooltipSurface,
          borderWidth: 0,
          textStyle: { color: theme.onTooltip },
          axisPointer: { type: "line" as const, lineStyle: { color: theme.axis, type: "dashed" as const } },
          formatter: (params: unknown) => {
            const first = Array.isArray(params) ? (params[0] as { dataIndex?: number }) : undefined;
            const p = points[first?.dataIndex ?? 0];
            return p ? `${dateLabel.format(new Date(p.date))}<br/><b>${formatMoney(p.value, currency, locale).text}</b>` : "";
          },
        },
        xAxis: {
          type: "category" as const,
          boundaryGap: false,
          data: points.map((p) => dateLabel.format(new Date(p.date))),
          axisLine: { lineStyle: { color: theme.grid } },
          axisTick: { show: false },
          axisLabel: { color: theme.axis, hideOverlap: true },
        },
        yAxis: {
          type: "value" as const,
          scale: true,
          splitLine: { lineStyle: { color: theme.grid } },
          axisLabel: { color: theme.axis, formatter: (tick: number) => axisLabel.format(tick) },
        },
        series: [
          {
            type: "line" as const,
            data: points.map((p) => plotNumber(p.value)),
            showSymbol: false,
            lineStyle: { color: line, width: 2 },
            itemStyle: { color: line },
            areaStyle: { color: line, opacity: 0.12 },
          },
        ],
      };
    },
    [points, currency, locale, dateLabel, axisLabel],
  );

  return (
    <ChartFrame
      title={title}
      info={info}
      summary={summary}
      actions={actions}
      columns={["Date", `Value (${currency})`]}
      rows={points.map((p) => ({ label: dateLabel.format(new Date(p.date)), values: [formatMoney(p.value, currency, locale).text] }))}
    >
      <EChart build={build} height={height} />
    </ChartFrame>
  );
}
