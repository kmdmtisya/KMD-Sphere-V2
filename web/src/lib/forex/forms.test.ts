import { describe, expect, it } from "vitest";

import { emptyOrder, emptyRisk, orderRequest, riskRequest, validateOrder, validateRisk } from "./forms";

const risk = { ...emptyRisk("USD"), entry: "1.0850", stop: "1.0800" };

describe("risk form", () => {
  it("accepts a long with its stop below the entry", () => {
    expect(validateRisk(risk)).toEqual({});
  });
  it("refuses a stop on the wrong side of the entry, for either direction", () => {
    expect(validateRisk({ ...risk, stop: "1.0900" }).stop).toMatch(/below the entry/);
    expect(validateRisk({ ...risk, direction: "short" }).stop).toMatch(/above the entry/);
    expect(validateRisk({ ...risk, direction: "short", stop: "1.0900" })).toEqual({});
  });
  it("needs prices, a balance and a risk share, as decimal text", () => {
    expect(Object.keys(validateRisk(emptyRisk("USD"))).sort()).toEqual(["entry", "stop"]);
    expect(validateRisk({ ...risk, balance: "10,000" }).balance).toBeTruthy();
    expect(validateRisk({ ...risk, riskPercent: "0" }).riskPercent).toBeTruthy();
    expect(validateRisk({ ...risk, target: "abc" }).target).toBeTruthy();
  });
  it("sends strings and an empty target as null", () => {
    expect(riskRequest(risk)).toMatchObject({ instrument: "EUR_USD", entry: "1.0850", stop: "1.0800", target: null, balance: "10000", account_currency: "USD", risk_percent: "1" });
  });
});

describe("paper order form", () => {
  it("requires a stop and a size", () => {
    expect(Object.keys(validateOrder(emptyOrder()))).toEqual(["stop"]);
    expect(validateOrder({ ...emptyOrder(), stop: "1.08", lots: "0" }).lots).toBeTruthy();
    expect(validateOrder({ ...emptyOrder(), stop: "1.08" })).toEqual({});
  });
  it("is always a market order on paper with a decimal-string request", () => {
    expect(orderRequest({ ...emptyOrder(), stop: "1.0800", tag: " breakout " })).toEqual({ instrument: "EUR_USD", side: "long", order_type: "market", lots: "0.10", stop: "1.0800", target: null, strategy_tag: "breakout" });
  });
});
