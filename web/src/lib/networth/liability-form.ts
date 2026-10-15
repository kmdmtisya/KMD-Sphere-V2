/**
 * The liability form (P14-T11.1): typed text becomes a request; nothing is calculated here. The
 * backend validates (limits, dates, ownership) and stays the authority.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];
export type LiabilityType = S["LiabilityCreate"]["liability_type"];

export const LIABILITY_TYPES: { value: LiabilityType; label: string }[] = [
  { value: "mortgage", label: "Mortgage" },
  { value: "personal_loan", label: "Personal loan" },
  { value: "car_loan", label: "Car loan" },
  { value: "student_loan", label: "Student loan" },
  { value: "business_loan", label: "Business loan" },
  { value: "credit_card", label: "Credit card" },
  { value: "other", label: "Other" },
];

export type LiabilityValues = {
  name: string;
  type: LiabilityType;
  balance: string;
  currency: string;
  asOf: string;
  rate: string;
};

export function emptyLiability(
  currency: string,
  today: string,
): LiabilityValues {
  return {
    name: "",
    type: "mortgage",
    balance: "",
    currency,
    asOf: today,
    rate: "",
  };
}

export function liabilityFromApi(l: S["LiabilityOut"]): LiabilityValues {
  return {
    name: l.name,
    type: l.liability_type,
    balance: l.balance.amount,
    currency: l.balance.currency,
    asOf: l.balance_as_of,
    rate: l.interest_rate_percent ?? "",
  };
}

const AMOUNT = /^\d{1,10}(\.\d{1,12})?$/;
const RATE = /^(100(\.0{1,2})?|\d{1,2}(\.\d{1,2})?)$/; // 0 to 100, at most 2 decimals

export function validateLiability(
  v: LiabilityValues,
  today: string,
): Partial<Record<keyof LiabilityValues, string>> {
  const p: Partial<Record<keyof LiabilityValues, string>> = {};
  if (!v.name.trim()) p.name = "Give the liability a name.";
  if (!AMOUNT.test(v.balance))
    p.balance = "Enter the amount you owe (0 or more).";
  if (!/^[A-Z]{3}$/.test(v.currency)) p.currency = "Choose a currency.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.asOf))
    p.asOf = "Enter the date of this balance.";
  else if (v.asOf > today) p.asOf = "The balance date cannot be in the future.";
  if (v.rate && !RATE.test(v.rate))
    p.rate =
      "Enter a rate from 0 to 100 with up to 2 decimals, or leave blank.";
  return p;
}

export function liabilityRequest(v: LiabilityValues): S["LiabilityCreate"] {
  return {
    name: v.name.trim(),
    liability_type: v.type,
    balance: { amount: v.balance, currency: v.currency },
    balance_as_of: v.asOf,
    interest_rate_percent: v.rate || null,
  };
}
