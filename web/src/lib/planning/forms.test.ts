import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api";

import {
  defaultPlan,
  emptyGoal,
  goalFromApi,
  goalRequest,
  scenarioRequest,
  validateGoal,
  validatePlan,
} from "./forms";

describe("calculator form", () => {
  it("accepts the defaults", () => {
    expect(validatePlan(defaultPlan())).toEqual({});
  });
  it("refuses years outside 1 to 60 and malformed numbers", () => {
    expect(validatePlan({ ...defaultPlan(), years: "0" }).years).toBeTruthy();
    expect(validatePlan({ ...defaultPlan(), years: "61" }).years).toBeTruthy();
    expect(validatePlan({ ...defaultPlan(), years: "2.5" }).years).toBeTruthy();
    expect(
      validatePlan({ ...defaultPlan(), initial: "1,000" }).initial,
    ).toBeTruthy();
    expect(
      validatePlan({ ...defaultPlan(), contribution: "-5" }).contribution,
    ).toBeTruthy();
  });
  it("keeps the cautious rate at or below base and the optimistic at or above", () => {
    expect(
      validatePlan({ ...defaultPlan(), conservative: "8" }).conservative,
    ).toBeTruthy();
    expect(validatePlan({ ...defaultPlan(), growth: "5" }).growth).toBeTruthy();
  });
  it("sends decimal strings in the chosen currency, with nothing calculated", () => {
    const r = scenarioRequest({ ...defaultPlan(), initial: "1234.50" }, "EUR");
    expect(r.initial_investment).toEqual({
      amount: "1234.50",
      currency: "EUR",
    });
    expect(r.years).toBe(20);
    expect(r.annual_return_percent).toBe("7");
    expect(r.conservative_return_percent).toBe("4");
  });
});

describe("goal form", () => {
  const ok = {
    ...emptyGoal(),
    name: "House",
    target: "50000",
    targetDate: "2030-01-01",
  };
  it("needs a name, a target and a future date", () => {
    expect(Object.keys(validateGoal(emptyGoal(), "2026-10-15")).sort()).toEqual(
      ["name", "target", "targetDate"],
    );
    expect(validateGoal(ok, "2026-10-15")).toEqual({});
    expect(
      validateGoal({ ...ok, targetDate: "2026-10-15" }, "2026-10-15")
        .targetDate,
    ).toMatch(/future/);
    expect(
      validateGoal({ ...ok, target: "0" }, "2026-10-15").target,
    ).toBeTruthy();
  });
  it("round-trips through the API shape, leaving optional rates null when blank", () => {
    const req = goalRequest(ok, "USD");
    expect(req.assumptions.returns).toEqual({
      base: "7",
      conservative: null,
      growth: null,
    });
    expect(req.portfolio_id).toBeNull();
    const out = {
      ...req,
      id: "g",
      created_at: "",
      updated_at: "",
      goal_type: "wealth",
      target_in_todays_money: false,
      portfolio_id: null,
    } as unknown as components["schemas"]["GoalOut"];
    expect(goalFromApi(out).name).toBe("House");
    expect(goalFromApi(out).target).toBe("50000");
  });
});
