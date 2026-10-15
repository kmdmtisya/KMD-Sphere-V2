/**
 * Calculator and goal forms (P14-T10): the typed text becomes a request, and nothing is calculated
 * here. The backend forecast engine is the authority (QG-30.4); these checks only avoid sending
 * what it would refuse. Every amount and rate stays a decimal string.
 */
import type { components } from "@/lib/api";

type S = components["schemas"];
export type Frequency = S["Frequency"];
export const FREQUENCIES: { value: Frequency; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
];

const UNSIGNED = /^\d{1,20}(\.\d{1,12})?$/;
const SIGNED = /^-?\d{1,20}(\.\d{1,12})?$/;

export type PlanValues = {
  initial: string;
  contribution: string;
  contributionFrequency: Frequency;
  contributionGrowth: string;
  years: string;
  base: string;
  conservative: string;
  growth: string;
  inflation: string;
  fee: string;
  compounding: Frequency;
};

export function defaultPlan(): PlanValues {
  return {
    initial: "10000",
    contribution: "500",
    contributionFrequency: "monthly",
    contributionGrowth: "0",
    years: "20",
    base: "7",
    conservative: "4",
    growth: "10",
    inflation: "2.5",
    fee: "0",
    compounding: "monthly",
  };
}

export type Problems<T> = Partial<Record<keyof T, string>>;

/** What is wrong with the calculator form, field by field (empty when it can be sent). */
export function validatePlan(v: PlanValues): Problems<PlanValues> {
  const p: Problems<PlanValues> = {};
  if (!UNSIGNED.test(v.initial))
    p.initial = "Enter the amount you start with (0 or more).";
  if (!UNSIGNED.test(v.contribution))
    p.contribution = "Enter the amount you add each period (0 or more).";
  if (!/^\d+$/.test(v.years) || Number(v.years) < 1 || Number(v.years) > 60)
    p.years = "Enter whole years from 1 to 60.";
  for (const key of ["base", "conservative", "growth"] as const)
    if (!SIGNED.test(v[key])) p[key] = "Enter a yearly rate, for example 7.";
  for (const key of ["contributionGrowth", "inflation", "fee"] as const)
    if (!SIGNED.test(v[key])) p[key] = "Enter a yearly rate, for example 2.5.";
  if (!p.conservative && !p.base && !p.growth) {
    // Only the order of three rates is compared; no money is calculated.
    const cautious = Number(v.conservative);
    const base = Number(v.base);
    const optimistic = Number(v.growth);
    if (cautious > base)
      p.conservative = "The cautious rate should not be above the base rate.";
    else if (optimistic < base)
      p.growth = "The optimistic rate should not be below the base rate.";
  }
  return p;
}

export function scenarioRequest(
  v: PlanValues,
  currency: string,
): S["ScenarioForecastIn"] {
  return {
    initial_investment: { amount: v.initial, currency },
    contribution: { amount: v.contribution, currency },
    contribution_frequency: v.contributionFrequency,
    contribution_growth_percent: v.contributionGrowth,
    compounding_frequency: v.compounding,
    years: Number(v.years),
    annual_return_percent: v.base,
    conservative_return_percent: v.conservative,
    growth_return_percent: v.growth,
    inflation_percent: v.inflation,
    annual_fee_percent: v.fee,
  };
}

export type GoalValues = {
  name: string;
  type: NonNullable<S["GoalCreate"]["goal_type"]>;
  target: string;
  targetDate: string;
  todaysMoney: boolean;
  portfolioId: string;
  contribution: string;
  contributionFrequency: Frequency;
  base: string;
  conservative: string;
  growth: string;
  inflation: string;
};

export const GOAL_TYPES: { value: GoalValues["type"]; label: string }[] = [
  { value: "wealth", label: "Build wealth" },
  { value: "retirement", label: "Retirement" },
  { value: "education", label: "Education" },
  { value: "house_deposit", label: "House deposit" },
  { value: "business_capital", label: "Business capital" },
  { value: "custom", label: "Other" },
];

export function emptyGoal(): GoalValues {
  return {
    name: "",
    type: "wealth",
    target: "",
    targetDate: "",
    todaysMoney: false,
    portfolioId: "",
    contribution: "0",
    contributionFrequency: "monthly",
    base: "7",
    conservative: "",
    growth: "",
    inflation: "2.5",
  };
}

export function goalFromApi(g: S["GoalOut"]): GoalValues {
  return {
    name: g.name,
    type: g.goal_type,
    target: g.target.amount,
    targetDate: g.target_date,
    todaysMoney: g.target_in_todays_money,
    portfolioId: g.portfolio_id ?? "",
    contribution: g.assumptions.contribution.amount,
    contributionFrequency: g.assumptions.contribution_frequency ?? "monthly",
    base: g.assumptions.returns.base,
    conservative: g.assumptions.returns.conservative ?? "",
    growth: g.assumptions.returns.growth ?? "",
    inflation: g.assumptions.inflation_percent ?? "0",
  };
}

export function validateGoal(
  v: GoalValues,
  today: string,
): Problems<GoalValues> {
  const p: Problems<GoalValues> = {};
  if (!v.name.trim()) p.name = "Give the goal a name.";
  if (!(UNSIGNED.test(v.target) && /[1-9]/.test(v.target)))
    p.target = "Enter a target amount above zero.";
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v.targetDate))
    p.targetDate = "Choose the date you want to reach it by.";
  else if (v.targetDate <= today) p.targetDate = "Choose a date in the future.";
  if (!UNSIGNED.test(v.contribution))
    p.contribution = "Enter what you add each period (0 or more).";
  if (!SIGNED.test(v.base)) p.base = "Enter a yearly rate, for example 7.";
  for (const key of ["conservative", "growth"] as const)
    if (v[key] && !SIGNED.test(v[key]))
      p[key] = "Enter a yearly rate or leave blank.";
  if (!SIGNED.test(v.inflation))
    p.inflation = "Enter a yearly rate, for example 2.5.";
  return p;
}

export function goalRequest(v: GoalValues, currency: string): S["GoalCreate"] {
  return {
    name: v.name.trim(),
    goal_type: v.type,
    target: { amount: v.target, currency },
    target_date: v.targetDate,
    target_in_todays_money: v.todaysMoney,
    portfolio_id: v.portfolioId || null,
    assumptions: {
      contribution: { amount: v.contribution, currency },
      contribution_frequency: v.contributionFrequency,
      contribution_growth_percent: "0",
      compounding_frequency: "monthly",
      annual_fee_percent: "0",
      inflation_percent: v.inflation,
      returns: {
        base: v.base,
        conservative: v.conservative || null,
        growth: v.growth || null,
      },
    },
  };
}
