"use client";

import { useCallback, useMemo } from "react";

import { plotNumber } from "@/lib/chart/plot-values";
import { formatMoney } from "@/lib/format/decimal";

import { ChartFrame } from "./ChartFrame";
import { EChart } from "./EChart";
import type { ChartTheme } from "./useChartTheme";

/**
 * Forecast scenarios side by side (conservative, base, growth) by year, as lines. Every value is the
 * backend's decimal string, shown exactly in the tooltip and the table; it is converted to a number
 * only to place the line. A projection, never a promise: the frame says so through its summary.
 */
export type ScenarioLine = {
  name: string;
  points: { year: number; value: string }[];
};

export function ScenarioLineChart({
  title,
  info,
  lines,
  currency,
  summary,
  locale = "en",
  height = 280,
}: {
  title: string;
  info?: string;
  lines: ScenarioLine[];
  currency: string;
  summary: string;
  locale?: string;
  height?: number;
}) {
  const years = useMemo(
    () => lines[0]?.points.map((p) => p.year) ?? [],
    [lines],
  );
  const axisLabel = useMemo(
    () =>
      new Intl.NumberFormat(locale, {
        style: "currency",
        currency,
        notation: "compact",
        maximumFractionDigits: 1,
      }),
    [locale, currency],
  );

  const build = useCallback(
    (theme: ChartTheme) => ({
      grid: { left: 8, right: 16, top: 32, bottom: 8, containLabel: true },
      legend: { top: 0, textStyle: { color: theme.axis } },
      tooltip: {
        trigger: "axis" as const,
        backgroundColor: theme.tooltipSurface,
        borderWidth: 0,
        textStyle: { color: theme.onTooltip },
        axisPointer: {
          type: "line" as const,
          lineStyle: { color: theme.axis, type: "dashed" as const },
        },
        formatter: (params: unknown) => {
          const first = Array.isArray(params)
            ? (params[0] as { dataIndex?: number })
            : undefined;
          const i = first?.dataIndex ?? 0;
          const rows = lines.map(
            (l) =>
              `${l.name}: <b>${formatMoney(l.points[i]?.value ?? "0", currency, locale).text}</b>`,
          );
          return [`Year ${years[i] ?? i}`, ...rows].join("<br/>");
        },
      },
      xAxis: {
        type: "category" as const,
        boundaryGap: false,
        data: years.map((y) => `Year ${y}`),
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: { color: theme.axis, hideOverlap: true },
      },
      yAxis: {
        type: "value" as const,
        scale: true,
        splitLine: { lineStyle: { color: theme.grid } },
        axisLabel: {
          color: theme.axis,
          formatter: (tick: number) => axisLabel.format(tick),
        },
      },
      series: lines.map((l, i) => ({
        type: "line" as const,
        name: l.name,
        data: l.points.map((p) => plotNumber(p.value)),
        showSymbol: false,
        lineStyle: { color: theme.series[i % theme.series.length], width: 2 },
        itemStyle: { color: theme.series[i % theme.series.length] },
      })),
    }),
    [lines, years, currency, locale, axisLabel],
  );

  return (
    <ChartFrame
      title={title}
      info={info}
      summary={summary}
      columns={["Year", ...lines.map((l) => `${l.name} (${currency})`)]}
      rows={years.map((y, i) => ({
        label: `Year ${y}`,
        values: lines.map(
          (l) => formatMoney(l.points[i]?.value ?? "0", currency, locale).text,
        ),
      }))}
    >
      <EChart build={build} height={height} />
    </ChartFrame>
  );
}
