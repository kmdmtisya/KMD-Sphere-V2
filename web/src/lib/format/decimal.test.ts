import { describe, expect, it } from "vitest";

import { absoluteOf, compareDecimalStrings, formatMoney, formatPercent, signOf } from "./decimal";

describe("signOf", () => {
  it("reads the sign from the string", () => {
    expect(signOf("12.50")).toBe("positive");
    expect(signOf("-0.01")).toBe("negative");
    expect(signOf("0")).toBe("zero");
    expect(signOf("-0.000")).toBe("zero");
    expect(() => signOf("1e3")).toThrow();
    expect(() => signOf("12,50")).toThrow();
  });

  it("drops the minus sign for the absolute value", () => {
    expect(absoluteOf("-17286.35")).toBe("17286.35");
    expect(absoluteOf("4.2")).toBe("4.2");
  });
});

describe("compareDecimalStrings", () => {
  it("orders exactly, including values a binary float cannot tell apart", () => {
    const values = ["10", "-2.5", "0.1", "9.99", "-10", "0", "100.00", "9.990"];
    const sorted = [...values].sort(compareDecimalStrings);
    expect(sorted).toEqual(["-10", "-2.5", "0", "0.1", "9.99", "9.990", "10", "100.00"]);
    expect(compareDecimalStrings("9007199254740993.01", "9007199254740993.02")).toBe(-1);
    expect(compareDecimalStrings("0.30000000000000000001", "0.3")).toBe(1);
    expect(compareDecimalStrings("007.50", "7.5")).toBe(0);
  });
});

describe("formatMoney", () => {
  it("formats the decimal string exactly and splits the minor part", () => {
    expect(formatMoney("325980.65", "USD")).toEqual({ text: "$325,980.65", major: "$325,980", minor: ".65" });
    expect(formatMoney("-1234.5", "EUR").text).toBe("-€1,234.50");
    expect(formatMoney("9007199254740993.01", "USD").text).toBe("$9,007,199,254,740,993.01");
  });

  it("keeps a currency suffix with the major part", () => {
    const parts = formatMoney("1234.56", "EUR", "de");
    const spaces = (s: string) => s.replace(/\s/g, " ");
    expect(spaces(parts.text)).toBe("1.234,56 €");
    expect(spaces(parts.major)).toBe("1.234 €");
    expect(parts.minor).toBe(",56");
  });

  it("handles currencies without a minor unit", () => {
    expect(formatMoney("1500", "JPY")).toEqual({ text: "¥1,500", major: "¥1,500", minor: "" });
  });
});

describe("formatPercent", () => {
  it("formats a decimal string as a percentage", () => {
    expect(formatPercent("14.09")).toBe("14.09%");
    expect(formatPercent("-3.1")).toBe("-3.10%");
  });
});
