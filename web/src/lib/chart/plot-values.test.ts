import { describe, expect, it } from "vitest";

import { plotNumber } from "./plot-values";

describe("plotNumber", () => {
  it("turns a decimal string into a chart coordinate", () => {
    expect(plotNumber("139986.35")).toBeCloseTo(139986.35);
    expect(plotNumber("-2.5")).toBe(-2.5);
  });

  it("refuses values that are not numbers", () => {
    expect(() => plotNumber("n/a")).toThrow();
    expect(() => plotNumber("Infinity")).toThrow();
  });
});
