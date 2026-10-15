"use client";

import { useEffect, useMemo, useRef, type RefObject } from "react";

import { echarts } from "./echarts";
import { useChartTheme, type ChartTheme } from "./useChartTheme";

export type EChartOption = Parameters<ReturnType<typeof echarts.init>["setOption"]>[0];

/**
 * Mounts an ECharts instance in `ref`, applies `option` whenever it changes (for example when the
 * theme changes) and resizes with its container. Animation is off: charts appear at once and
 * respect reduced motion.
 */
function useEChart(ref: RefObject<HTMLDivElement | null>, option: EChartOption | null) {
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const instance = echarts.init(el, undefined, { renderer: "svg" });
    chart.current = instance;
    const observer = new ResizeObserver(() => instance.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      instance.dispose();
      chart.current = null;
    };
  }, [ref]);

  useEffect(() => {
    if (option && chart.current) chart.current.setOption({ animation: false, ...option }, true);
  }, [option]);
}

/**
 * An ECharts chart that follows the active theme. `build` turns the resolved token colours into the
 * chart option; keep it stable (useCallback) so the chart redraws only when data or theme change.
 */
export function EChart({ build, height }: { build: (theme: ChartTheme) => EChartOption; height: number }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const theme = useChartTheme(ref);
  const option = useMemo(() => (theme ? build(theme) : null), [theme, build]);
  useEChart(ref, option);
  return <div ref={ref} style={{ height }} className="w-full" />;
}
