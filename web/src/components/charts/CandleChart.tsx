"use client";

import { useCallback, useMemo } from "react";

import { plotNumber } from "@/lib/chart/plot-values";

import { ChartFrame } from "./ChartFrame";
import { EChart } from "./EChart";
import type { ChartTheme } from "./useChartTheme";

/**
 * Candles with optional indicator lines (P14-T24.1). Prices are the API's decimal strings: shown
 * exactly in the tooltip and the table alternative, converted only to place the candles. Up and
 * down candles differ by fill and outline, not by colour alone.
 */
export type CandlePoint = {
  ts: string;
  open: string;
  high: string;
  low: string;
  close: string;
};
export type IndicatorLine = { name: string; values: (string | null)[] };

export function CandleChart({
  title,
  info,
  candles,
  indicators = [],
  summary,
  height = 320,
}: {
  title: string;
  info?: string;
  candles: CandlePoint[];
  indicators?: IndicatorLine[];
  summary: string;
  height?: number;
}) {
  const labels = useMemo(
    () => candles.map((c) => c.ts.slice(0, 16).replace("T", " ")),
    [candles],
  );
  const build = useCallback(
    (theme: ChartTheme) => ({
      grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
      legend: indicators.length
        ? { top: 0, textStyle: { color: theme.axis } }
        : undefined,
      tooltip: {
        trigger: "axis" as const,
        backgroundColor: theme.tooltipSurface,
        borderWidth: 0,
        textStyle: { color: theme.onTooltip },
        formatter: (params: unknown) => {
          const first = Array.isArray(params)
            ? (params[0] as { dataIndex?: number })
            : undefined;
          const i = first?.dataIndex ?? 0;
          const c = candles[i];
          if (!c) return "";
          const lines = indicators.map(
            (l) => `${l.name}: ${l.values[i] ?? "n/a"}`,
          );
          return [
            labels[i],
            `Open ${c.open}  High ${c.high}`,
            `Low ${c.low}  Close ${c.close}`,
            ...lines,
          ].join("<br/>");
        },
      },
      xAxis: {
        type: "category" as const,
        data: labels,
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: { color: theme.axis, hideOverlap: true },
      },
      yAxis: {
        type: "value" as const,
        scale: true,
        splitLine: { lineStyle: { color: theme.grid } },
        axisLabel: { color: theme.axis },
      },
      series: [
        {
          type: "candlestick" as const,
          name: "Price",
          data: candles.map((c) => [
            plotNumber(c.open),
            plotNumber(c.close),
            plotNumber(c.low),
            plotNumber(c.high),
          ]),
          // Up: filled; down: hollow with a thick outline (not colour alone).
          itemStyle: {
            color: theme.positive,
            color0: theme.surface,
            borderColor: theme.positive,
            borderColor0: theme.negative,
            borderWidth: 1.5,
          },
        },
        ...indicators.map((l, i) => ({
          type: "line" as const,
          name: l.name,
          data: l.values.map((v) => (v === null ? null : plotNumber(v))),
          showSymbol: false,
          lineStyle: {
            color: theme.series[(i + 3) % theme.series.length],
            width: 1.5,
          },
          itemStyle: { color: theme.series[(i + 3) % theme.series.length] },
        })),
      ],
    }),
    [candles, indicators, labels],
  );
  return (
    <ChartFrame
      title={title}
      info={info}
      summary={summary}
      columns={[
        "Time",
        "Open",
        "High",
        "Low",
        "Close",
        ...indicators.map((l) => l.name),
      ]}
      rows={candles.map((c, i) => ({
        label: labels[i],
        values: [
          c.open,
          c.high,
          c.low,
          c.close,
          ...indicators.map((l) => l.values[i] ?? "n/a"),
        ],
      }))}
    >
      <EChart build={build} height={height} />
    </ChartFrame>
  );
}
