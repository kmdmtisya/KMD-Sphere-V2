/**
 * The alert form (P14-T16.3): typed text becomes an alert request. The backend validates and stays
 * the authority; these checks only avoid sending what it would refuse. Prices and percentages stay
 * decimal strings.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];
export type AlertType = S["AlertCreate"]["alert_type"];

export const ALERT_TYPES: { value: AlertType; label: string; help: string }[] =
  [
    {
      value: "price_above",
      label: "Price rises above",
      help: "Tell me when the latest price is above this.",
    },
    {
      value: "price_below",
      label: "Price falls below",
      help: "Tell me when the latest price is below this.",
    },
    {
      value: "allocation_above",
      label: "Allocation rises above",
      help: "Tell me when an asset class is more than this share of a portfolio.",
    },
  ];

export type AlertValues = {
  type: AlertType;
  assetId: string;
  currency: string;
  price: string;
  portfolioId: string;
  assetClass: string;
  percent: string;
  note: string;
};

export const emptyAlert = (): AlertValues => ({
  type: "price_above",
  assetId: "",
  currency: "",
  price: "",
  portfolioId: "",
  assetClass: "",
  percent: "",
  note: "",
});

const PRICE = /^\d{1,20}(\.\d{1,12})?$/;
const PERCENT = /^(100(\.0{1,2})?|\d{1,2}(\.\d{1,2})?)$/;

export function validateAlert(
  v: AlertValues,
): Partial<Record<keyof AlertValues, string>> {
  const p: Partial<Record<keyof AlertValues, string>> = {};
  if (v.type === "allocation_above") {
    if (!v.portfolioId) p.portfolioId = "Choose the portfolio.";
    if (!v.assetClass) p.assetClass = "Choose the asset class.";
    if (!PERCENT.test(v.percent) || !/[1-9]/.test(v.percent))
      p.percent = "Enter a share above 0 and up to 100.";
  } else {
    if (!v.assetId) p.assetId = "Choose the asset.";
    if (!PRICE.test(v.price) || !/[1-9]/.test(v.price))
      p.price = "Enter a price above zero.";
    if (v.assetId && !/^[A-Z]{3}$/.test(v.currency))
      p.currency = "The asset's currency could not be read.";
  }
  if (v.note.length > 200) p.note = "Use 200 characters or fewer.";
  return p;
}

export function alertRequest(v: AlertValues): S["AlertCreate"] {
  const body: S["AlertCreate"] = { alert_type: v.type };
  if (v.type === "allocation_above") {
    body.portfolio_id = v.portfolioId;
    body.asset_class = v.assetClass;
    body.threshold_percent = v.percent;
  } else {
    body.asset_id = v.assetId;
    body.threshold_price = { amount: v.price, currency: v.currency };
  }
  if (v.note.trim()) body.note = v.note.trim();
  return body;
}
