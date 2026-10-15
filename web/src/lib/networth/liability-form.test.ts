import { describe, expect, it } from "vitest";

import {
  emptyLiability,
  liabilityRequest,
  validateLiability,
} from "./liability-form";

const TODAY = "2026-10-15";

describe("liability form", () => {
  it("needs a name, an amount and a date", () => {
    expect(
      Object.keys(
        validateLiability({ ...emptyLiability("USD", TODAY), asOf: "" }, TODAY),
      ).sort(),
    ).toEqual(["asOf", "balance", "name"]);
  });
  it("accepts zero (paid off) and refuses a future date, a negative or malformed amount and a bad rate", () => {
    const ok = { ...emptyLiability("USD", TODAY), name: "Home", balance: "0" };
    expect(validateLiability(ok, TODAY)).toEqual({});
    expect(
      validateLiability({ ...ok, asOf: "2026-10-16" }, TODAY).asOf,
    ).toBeTruthy();
    expect(
      validateLiability({ ...ok, balance: "-5" }, TODAY).balance,
    ).toBeTruthy();
    expect(
      validateLiability({ ...ok, balance: "1,000" }, TODAY).balance,
    ).toBeTruthy();
    expect(
      validateLiability({ ...ok, rate: "100.5" }, TODAY).rate,
    ).toBeTruthy();
    expect(
      validateLiability({ ...ok, rate: "4.125" }, TODAY).rate,
    ).toBeTruthy();
    expect(validateLiability({ ...ok, rate: "4.25" }, TODAY)).toEqual({});
  });
  it("sends the amount as a decimal string and an empty rate as null", () => {
    const body = liabilityRequest({
      ...emptyLiability("EUR", TODAY),
      name: " Home ",
      balance: "150000.50",
    });
    expect(body).toMatchObject({
      name: "Home",
      liability_type: "mortgage",
      balance: { amount: "150000.50", currency: "EUR" },
      balance_as_of: TODAY,
      interest_rate_percent: null,
    });
  });
});
