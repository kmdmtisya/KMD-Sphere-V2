/**
 * The one place in the web client where a decimal string becomes a binary float: to place a point on
 * a chart. It is display geometry only. Tooltips, labels, summaries and the "view as table" option
 * always show the original decimal string from the API, and nothing is calculated from these numbers
 * (ADR-0003, QG-26.3). This file is exempt from `wealthsphere/no-money-arithmetic` in
 * eslint.config.mjs for that reason alone.
 */
export function plotNumber(value: string): number {
  const n = Number(value);
  if (!Number.isFinite(n)) throw new Error(`not a plottable decimal string: ${value}`);
  return n;
}
