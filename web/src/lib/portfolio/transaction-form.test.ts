import { describe, expect, it } from "vitest";

import { emptyForm, TYPE_RULES, TYPES, toRequest, validate } from "./transaction-form";

const base = (over: Partial<ReturnType<typeof emptyForm>>) => ({ ...emptyForm("USD", "2026-10-15"), ...over });

describe("transaction form", () => {
  it("covers every transaction type the API accepts", () => {
    expect(TYPES).toHaveLength(14);
    for (const t of TYPES) expect(TYPE_RULES[t].label).toBeTruthy();
  });

  it("requires what the backend rules require, per type", () => {
    expect(Object.keys(validate(base({ type: "BUY" }), "USD")).sort()).toEqual(["assetId", "quantity", "unitPrice"]);
    expect(Object.keys(validate(base({ type: "DEPOSIT" }), "USD"))).toEqual(["gross"]);
    expect(Object.keys(validate(base({ type: "DIVIDEND" }), "USD")).sort()).toEqual(["assetId", "gross"]);
    expect(validate(base({ type: "FEE", gross: "5.00" }), "USD")).toEqual({});
    expect(validate(base({ type: "DEPOSIT", gross: "100" }), "USD")).toEqual({});
  });

  it("accepts a negative amount only for a valuation adjustment", () => {
    expect(validate(base({ type: "VALUATION_ADJUSTMENT", assetId: "a", gross: "-250.50" }), "USD")).toEqual({});
    expect(validate(base({ type: "DEPOSIT", gross: "-5" }), "USD").gross).toBeTruthy();
  });

  it("rejects zero or malformed quantities and amounts", () => {
    expect(validate(base({ type: "BUY", assetId: "a", quantity: "0", unitPrice: "1" }), "USD").quantity).toBeTruthy();
    expect(validate(base({ type: "BUY", assetId: "a", quantity: "1e3", unitPrice: "1" }), "USD").quantity).toBeTruthy();
    expect(validate(base({ type: "DEPOSIT", gross: "12,50" }), "USD").gross).toBeTruthy();
    expect(validate(base({ type: "DEPOSIT", gross: "10", fees: "x" }), "USD").fees).toBeTruthy();
  });

  it("asks for the FX rate when the currency differs from the portfolio's", () => {
    const eur = base({ type: "DEPOSIT", gross: "100", currency: "EUR" });
    expect(validate(eur, "USD").fxRate).toMatch(/USD/);
    expect(validate({ ...eur, fxRate: "1.08" }, "USD")).toEqual({});
  });

  it("sends only the fields the type takes, as decimal strings, leaving a BUY's total to the server", () => {
    const body = toRequest(base({ type: "BUY", assetId: "asset-1", quantity: "10", unitPrice: "12.5", gross: "999", note: " first lot " }), "USD");
    expect(body).toMatchObject({ transaction_type: "BUY", asset_id: "asset-1", quantity: "10", unit_price: { amount: "12.5", currency: "USD" }, note: "first lot" });
    expect(body.fx_rate_to_portfolio_currency).toBeUndefined();
    const deposit = toRequest(base({ type: "DEPOSIT", gross: "100", assetId: "ignored", quantity: "5" }), "USD");
    expect(deposit.asset_id).toBeUndefined();
    expect(deposit.quantity).toBeUndefined();
    expect(deposit.gross_amount).toEqual({ amount: "100", currency: "USD" });
  });

  it("adds the entered FX rate and its source for a foreign-currency posting", () => {
    const body = toRequest(base({ type: "DEPOSIT", gross: "100", currency: "EUR", fxRate: "1.08" }), "USD");
    expect(body.fx_rate_to_portfolio_currency).toBe("1.08");
    expect(body.fx_rate_source).toBe("entered by user");
    expect(body.fx_rate_as_of).toMatch(/Z$/);
  });
});
