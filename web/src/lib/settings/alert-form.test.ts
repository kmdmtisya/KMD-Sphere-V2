import { describe, expect, it } from "vitest";

import { alertRequest, emptyAlert, validateAlert } from "./alert-form";

describe("alert form", () => {
  it("a price alert needs an asset and a price", () => {
    expect(Object.keys(validateAlert(emptyAlert())).sort()).toEqual([
      "assetId",
      "price",
    ]);
    expect(
      validateAlert({
        ...emptyAlert(),
        assetId: "a",
        currency: "USD",
        price: "150.25",
      }),
    ).toEqual({});
    expect(
      validateAlert({
        ...emptyAlert(),
        assetId: "a",
        currency: "USD",
        price: "0",
      }).price,
    ).toBeTruthy();
    expect(
      validateAlert({
        ...emptyAlert(),
        assetId: "a",
        currency: "USD",
        price: "1,5",
      }).price,
    ).toBeTruthy();
  });
  it("an allocation alert needs a portfolio, a class and a share up to 100", () => {
    const base = { ...emptyAlert(), type: "allocation_above" as const };
    expect(Object.keys(validateAlert(base)).sort()).toEqual([
      "assetClass",
      "percent",
      "portfolioId",
    ]);
    expect(
      validateAlert({
        ...base,
        portfolioId: "p",
        assetClass: "equity",
        percent: "40",
      }),
    ).toEqual({});
    expect(
      validateAlert({
        ...base,
        portfolioId: "p",
        assetClass: "equity",
        percent: "100.5",
      }).percent,
    ).toBeTruthy();
    expect(
      validateAlert({
        ...base,
        portfolioId: "p",
        assetClass: "equity",
        percent: "0",
      }).percent,
    ).toBeTruthy();
  });
  it("sends the price as a decimal string in the asset's currency, and only the fields of its type", () => {
    const price = alertRequest({
      ...emptyAlert(),
      type: "price_below",
      assetId: "a",
      currency: "EUR",
      price: "9.5",
      note: " dip ",
    });
    expect(price).toEqual({
      alert_type: "price_below",
      asset_id: "a",
      threshold_price: { amount: "9.5", currency: "EUR" },
      note: "dip",
    });
    const alloc = alertRequest({
      ...emptyAlert(),
      type: "allocation_above",
      portfolioId: "p",
      assetClass: "equity",
      percent: "40",
      assetId: "ignored",
    });
    expect(alloc).toEqual({
      alert_type: "allocation_above",
      portfolio_id: "p",
      asset_class: "equity",
      threshold_percent: "40",
    });
  });
});
