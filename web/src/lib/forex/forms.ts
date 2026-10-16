/**
 * Forex workspace forms (P14-T24): the risk calculator and the paper order. Typed text becomes a
 * request; nothing is calculated here (the backend sizes the position and checks the order). All
 * prices and amounts stay decimal strings. A paper order is always simulated: no field here can
 * describe a real-money order.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];

const PRICE = /^\d{1,12}(\.\d{1,8})?$/;
const AMOUNT = /^\d{1,14}(\.\d{1,4})?$/;
const PERCENT = /^\d{1,2}(\.\d{1,4})?$/;
const LOTS = /^\d{1,6}(\.\d{1,2})?$/;
const POSITIVE = (v: string) => /[1-9]/.test(v);

export type RiskValues = { instrument: string; direction: "long" | "short"; entry: string; stop: string; target: string; balance: string; currency: string; riskPercent: string };
export type Problems<T> = Partial<Record<keyof T, string>>;

export const emptyRisk = (currency: string): RiskValues => ({ instrument: "EUR_USD", direction: "long", entry: "", stop: "", target: "", balance: "10000", currency, riskPercent: "1" });

export function validateRisk(v: RiskValues): Problems<RiskValues> {
  const p: Problems<RiskValues> = {};
  if (!/^[A-Z]{3}_[A-Z]{3}$/.test(v.instrument)) p.instrument = "Choose a pair.";
  if (!PRICE.test(v.entry) || !POSITIVE(v.entry)) p.entry = "Enter the entry price.";
  if (!PRICE.test(v.stop) || !POSITIVE(v.stop)) p.stop = "Enter the stop price.";
  if (!p.entry && !p.stop) {
    // Only the side of two prices is compared; the backend does the arithmetic.
    const wrongSide = v.direction === "long" ? Number(v.stop) >= Number(v.entry) : Number(v.stop) <= Number(v.entry);
    if (wrongSide) p.stop = v.direction === "long" ? "For a long position the stop is below the entry." : "For a short position the stop is above the entry.";
  }
  if (v.target && (!PRICE.test(v.target) || !POSITIVE(v.target))) p.target = "Enter a price or leave blank.";
  if (!AMOUNT.test(v.balance) || !POSITIVE(v.balance)) p.balance = "Enter your account balance.";
  if (!/^[A-Z]{3}$/.test(v.currency)) p.currency = "Choose a currency.";
  if (!PERCENT.test(v.riskPercent) || !POSITIVE(v.riskPercent)) p.riskPercent = "Enter the share of the balance you would risk, for example 1.";
  return p;
}

export function riskRequest(v: RiskValues): S["ForexRiskRequest"] {
  return { instrument: v.instrument, direction: v.direction, entry: v.entry, stop: v.stop, target: v.target || null, balance: v.balance, account_currency: v.currency, risk_percent: v.riskPercent };
}

export type OrderValues = { instrument: string; side: "long" | "short"; lots: string; stop: string; target: string; tag: string };
export const emptyOrder = (): OrderValues => ({ instrument: "EUR_USD", side: "long", lots: "0.10", stop: "", target: "", tag: "" });

export function validateOrder(v: OrderValues): Problems<OrderValues> {
  const p: Problems<OrderValues> = {};
  if (!/^[A-Z]{3}_[A-Z]{3}$/.test(v.instrument)) p.instrument = "Choose a pair.";
  if (!LOTS.test(v.lots) || !POSITIVE(v.lots)) p.lots = "Enter a size in lots, for example 0.10.";
  if (!PRICE.test(v.stop) || !POSITIVE(v.stop)) p.stop = "A stop price is required.";
  if (v.target && (!PRICE.test(v.target) || !POSITIVE(v.target))) p.target = "Enter a price or leave blank.";
  if (v.tag.length > 40) p.tag = "Use 40 characters or fewer.";
  return p;
}

export function orderRequest(v: OrderValues): S["ForexPaperOrderCreate"] {
  return { instrument: v.instrument, side: v.side, order_type: "market", lots: v.lots, stop: v.stop, target: v.target || null, strategy_tag: v.tag.trim() || null };
}
