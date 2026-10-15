import { describe, expect, it } from "vitest";

import { rangeParams } from "./Analytics";

describe("rangeParams", () => {
  const today = new Date("2026-10-15T12:00:00Z");
  it("starts each range the right time back, with a spacing that suits it", () => {
    expect(rangeParams("1M", today)).toEqual({
      start: "2026-09-15",
      frequency: "daily",
    });
    expect(rangeParams("3M", today)).toEqual({
      start: "2026-07-15",
      frequency: "weekly",
    });
    expect(rangeParams("1Y", today)).toEqual({
      start: "2025-10-15",
      frequency: "weekly",
    });
    expect(rangeParams("5Y", today)).toEqual({
      start: "2021-10-15",
      frequency: "monthly",
    });
  });
  it("leaves the start to the API for All", () => {
    expect(rangeParams("ALL", today)).toEqual({ frequency: "monthly" });
  });
});
