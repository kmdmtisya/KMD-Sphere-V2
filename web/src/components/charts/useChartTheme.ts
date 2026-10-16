"use client";

import { useCallback, useSyncExternalStore, type RefObject } from "react";

/**
 * Chart colours resolved from the design tokens for the element the chart sits in, so charts follow
 * Light, Dark and System (docs/web/WEB_THEME_SYSTEM.md §6). ECharts and Lightweight Charts take
 * colour values, not CSS variables, so the chart redraws when this changes: on a system appearance
 * change or when `data-theme-pref` changes on <html>.
 */
export type ChartTheme = {
  series: string[];
  text: string;
  axis: string;
  grid: string;
  surface: string;
  tooltipSurface: string;
  onTooltip: string;
  growth: string;
  contributions: string;
  positive: string;
  negative: string;
};

const SERIES_COUNT = 6;

function readTheme(el: Element): string {
  const s = getComputedStyle(el);
  const v = (name: string) => s.getPropertyValue(`--ws-${name}`).trim();
  const theme: ChartTheme = {
    series: Array.from({ length: SERIES_COUNT }, (_, i) => v(`series${i + 1}`)),
    text: v("text-primary"),
    axis: v("chart-axis"),
    grid: v("chart-grid"),
    surface: v("surface"),
    tooltipSurface: v("tooltip-surface"),
    onTooltip: v("on-tooltip"),
    growth: v("chart-growth"),
    contributions: v("chart-contributions"),
    positive: v("positive"),
    negative: v("negative"),
  };
  return JSON.stringify(theme);
}

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", onChange);
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme-pref"] });
  // The chart's element is attached only after the first render: read once it is.
  queueMicrotask(onChange);
  return () => {
    media.removeEventListener("change", onChange);
    observer.disconnect();
  };
}

/** The resolved chart theme for the element in `ref`, or null before it is mounted. */
export function useChartTheme(ref: RefObject<HTMLElement | null>): ChartTheme | null {
  const snapshot = useCallback(() => (ref.current ? readTheme(ref.current) : ""), [ref]);
  const value = useSyncExternalStore(subscribe, snapshot, () => "");
  return value ? (JSON.parse(value) as ChartTheme) : null;
}
