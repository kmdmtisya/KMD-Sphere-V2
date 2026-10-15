/**
 * DEMO sample data for the component gallery only. These figures are fictional, are labelled DEMO
 * wherever they appear, and never reach a real page (CLAUDE.md: mock values are explicitly labelled).
 * Values are decimal strings, exactly as the API sends them.
 */
import type { DistributionItem } from "@/components/charts/DistributionBar";
import type { ValuePoint } from "@/components/charts/PerformanceLineChart";

export const CURRENCY = "USD";

export const totalWealth = { value: "139986.35", changePercent: "14.09", changeAmount: "17286.35" };
export const netWorth = { value: "168286.35", changePercent: "-1.24", changeAmount: "-2114.80" };
export const income = { value: "1245.30", changePercent: "0.00", changeAmount: "0.00" };

export const wealthSeries: ValuePoint[] = [
  ["2026-09-09", "138520.10"],
  ["2026-09-12", "138790.44"],
  ["2026-09-15", "138004.18"],
  ["2026-09-18", "138610.92"],
  ["2026-09-21", "138890.05"],
  ["2026-09-24", "138742.66"],
  ["2026-09-27", "138488.31"],
  ["2026-09-30", "139120.77"],
  ["2026-10-03", "139602.40"],
  ["2026-10-06", "139871.02"],
  ["2026-10-09", "139986.35"],
].map(([date, value]) => ({ date, value }));

export const allocation: DistributionItem[] = [
  { label: "Listed shares", percent: "52.40", amount: "73352.85" },
  { label: "Bonds", percent: "21.10", amount: "29537.12" },
  { label: "Money market", percent: "14.30", amount: "20018.05" },
  { label: "Property", percent: "8.60", amount: "12038.83" },
  { label: "Cash", percent: "3.60", amount: "5039.50" },
];

export type HoldingRow = {
  id: string;
  name: string;
  assetClass: string;
  marketValue: string;
  currency: string;
  asOf: string;
};

export const holdings: HoldingRow[] = [
  { id: "h1", name: "DEMO Global Equity Fund", assetClass: "Listed shares", marketValue: "48210.40", currency: "USD", asOf: "2026-10-09" },
  { id: "h2", name: "DEMO Treasury Bond 2031", assetClass: "Bonds", marketValue: "29537.12", currency: "USD", asOf: "2026-10-08" },
  { id: "h3", name: "DEMO Money Market Fund", assetClass: "Money market", marketValue: "20018.05", currency: "USD", asOf: "2026-10-09" },
  { id: "h4", name: "DEMO Nairobi Apartment", assetClass: "Property", marketValue: "12038.83", currency: "USD", asOf: "2026-09-30" },
  { id: "h5", name: "DEMO Tech Leaders ETF", assetClass: "Listed shares", marketValue: "25142.45", currency: "USD", asOf: "2026-10-09" },
  { id: "h6", name: "DEMO Savings Account", assetClass: "Cash", marketValue: "5039.50", currency: "USD", asOf: "2026-10-09" },
];

export const notices = [
  "DEMO: example figures for the component gallery, not your accounts.",
  "Informational only, not financial advice. WealthSphere never places trades.",
];
