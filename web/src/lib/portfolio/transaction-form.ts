/**
 * The ledger posting form (P14-T08.3): which fields each transaction type takes, and how the typed
 * text becomes a request. These mirror the backend's rules (app/modules/transactions/rules.py), which
 * remain the authority: the form only avoids sending what the API would refuse. Every amount stays a
 * decimal string; nothing is calculated here (a BUY's gross amount is left to the server to derive).
 */
import type { components } from "@/lib/api";

export type TransactionType = components["schemas"]["TransactionCreate"]["transaction_type"];
export type Requirement = "required" | "optional" | "none";

export type TypeRules = { asset: Requirement; quantity: Requirement; unitPrice: Requirement; gross: Requirement; label: string; help: string };

export const TYPE_RULES: Record<TransactionType, TypeRules> = {
  BUY: { label: "Buy", asset: "required", quantity: "required", unitPrice: "required", gross: "optional", help: "Units bought and the price per unit. The total is worked out by the server." },
  SELL: { label: "Sell", asset: "required", quantity: "required", unitPrice: "required", gross: "optional", help: "Units sold and the price per unit. You cannot sell more than you hold." },
  DEPOSIT: { label: "Deposit", asset: "none", quantity: "none", unitPrice: "none", gross: "required", help: "Cash paid into the portfolio." },
  WITHDRAWAL: { label: "Withdrawal", asset: "none", quantity: "none", unitPrice: "none", gross: "required", help: "Cash taken out of the portfolio." },
  DIVIDEND: { label: "Dividend", asset: "required", quantity: "none", unitPrice: "none", gross: "required", help: "Income paid by an asset you hold." },
  INTEREST: { label: "Interest", asset: "optional", quantity: "none", unitPrice: "none", gross: "required", help: "Interest received, on an asset or on cash." },
  COUPON: { label: "Coupon", asset: "required", quantity: "none", unitPrice: "none", gross: "required", help: "A bond coupon payment." },
  RENT: { label: "Rent", asset: "required", quantity: "none", unitPrice: "none", gross: "required", help: "Rent received on a property." },
  DISTRIBUTION: { label: "Distribution", asset: "required", quantity: "none", unitPrice: "none", gross: "required", help: "A fund distribution." },
  FEE: { label: "Fee", asset: "optional", quantity: "none", unitPrice: "none", gross: "required", help: "A fee you paid." },
  TAX: { label: "Tax", asset: "optional", quantity: "none", unitPrice: "none", gross: "required", help: "Tax you paid." },
  TRANSFER_IN: { label: "Transfer in", asset: "required", quantity: "required", unitPrice: "optional", gross: "required", help: "Units moved in from elsewhere; the amount is the value moved." },
  TRANSFER_OUT: { label: "Transfer out", asset: "required", quantity: "required", unitPrice: "optional", gross: "required", help: "Units moved out; the amount is the value moved." },
  VALUATION_ADJUSTMENT: { label: "Valuation adjustment", asset: "required", quantity: "none", unitPrice: "none", gross: "required", help: "A correction to an asset's value (may be negative)." },
};

export const TYPES = Object.keys(TYPE_RULES) as TransactionType[];

export type FormValues = {
  type: TransactionType;
  tradeDate: string;
  assetId: string;
  currency: string;
  quantity: string;
  unitPrice: string;
  gross: string;
  fees: string;
  taxes: string;
  fxRate: string;
  note: string;
};

const DECIMAL = /^\d+(\.\d+)?$/;
const SIGNED = /^-?\d+(\.\d+)?$/;
const CURRENCY = /^[A-Z]{3}$/;

/** What is wrong with the form, field by field (empty when it can be sent). */
export function validate(values: FormValues, portfolioCurrency: string): Partial<Record<keyof FormValues, string>> {
  const rules = TYPE_RULES[values.type];
  const problems: Partial<Record<keyof FormValues, string>> = {};
  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.tradeDate)) problems.tradeDate = "Enter the date.";
  if (!CURRENCY.test(values.currency)) problems.currency = "Choose a currency.";
  if (rules.asset === "required" && !values.assetId) problems.assetId = "Choose the asset.";
  if (rules.quantity === "required" && !(DECIMAL.test(values.quantity) && /[1-9]/.test(values.quantity))) problems.quantity = "Enter a quantity above zero.";
  if (rules.unitPrice === "required" && !DECIMAL.test(values.unitPrice)) problems.unitPrice = "Enter the price per unit.";
  if (values.unitPrice && !DECIMAL.test(values.unitPrice)) problems.unitPrice = "Use digits and a decimal point.";
  const grossPattern = values.type === "VALUATION_ADJUSTMENT" ? SIGNED : DECIMAL;
  if (rules.gross === "required" && !grossPattern.test(values.gross)) problems.gross = "Enter the amount.";
  if (values.gross && !grossPattern.test(values.gross)) problems.gross = "Use digits and a decimal point.";
  for (const key of ["fees", "taxes"] as const) if (values[key] && !DECIMAL.test(values[key])) problems[key] = "Use digits and a decimal point.";
  if (values.currency !== portfolioCurrency && !DECIMAL.test(values.fxRate)) problems.fxRate = `Enter the rate to ${portfolioCurrency} (1 ${values.currency || "unit"} = ? ${portfolioCurrency}).`;
  return problems;
}

/** The API request for the form (only the fields the type takes). */
export function toRequest(values: FormValues, portfolioCurrency: string): components["schemas"]["TransactionCreate"] {
  const rules = TYPE_RULES[values.type];
  const money = (amount: string) => ({ amount, currency: values.currency });
  const body: components["schemas"]["TransactionCreate"] = {
    transaction_type: values.type,
    trade_date: values.tradeDate,
    currency: values.currency,
  };
  if (rules.asset !== "none" && values.assetId) body.asset_id = values.assetId;
  if (rules.quantity !== "none" && values.quantity) body.quantity = values.quantity;
  if (rules.unitPrice !== "none" && values.unitPrice) body.unit_price = money(values.unitPrice);
  if (rules.gross !== "none" && values.gross) body.gross_amount = money(values.gross);
  if (values.fees) body.fees = money(values.fees);
  if (values.taxes) body.taxes = money(values.taxes);
  if (values.currency !== portfolioCurrency) {
    body.fx_rate_to_portfolio_currency = values.fxRate;
    body.fx_rate_source = "entered by user";
    body.fx_rate_as_of = new Date().toISOString();
  }
  if (values.note.trim()) body.note = values.note.trim();
  return body;
}

export function emptyForm(portfolioCurrency: string, today: string): FormValues {
  return { type: "BUY", tradeDate: today, assetId: "", currency: portfolioCurrency, quantity: "", unitPrice: "", gross: "", fees: "", taxes: "", fxRate: "", note: "" };
}
