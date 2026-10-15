import { describe, expect, it } from "vitest";

import { apiPathFor } from "./allowlist";

describe("apiPathFor", () => {
  it("maps plain segments under /api/v1", () => {
    expect(apiPathFor("GET", ["portfolios"])).toBe("/api/v1/portfolios");
    expect(apiPathFor("POST", ["portfolios", "7d3c0f2e-1b2a-4c5d-8e9f-0a1b2c3d4e5f", "transactions"])).toBe(
      "/api/v1/portfolios/7d3c0f2e-1b2a-4c5d-8e9f-0a1b2c3d4e5f/transactions",
    );
    expect(apiPathFor("GET", ["forex", "quotes"])).toBe("/api/v1/forex/quotes");
  });

  it.each([
    ["traversal", ["..", "admin"]],
    ["dot segment", ["."]],
    ["slash inside a decoded segment", ["a/b"]],
    ["backslash", ["a\\b"]],
    ["scheme", ["https:", "", "evil.example"]],
    ["empty segment", [""]],
    ["query characters", ["portfolios?x=1"]],
    ["percent sign", ["%2e%2e"]],
    ["whitespace", ["a b"]],
  ])("refuses %s", (_label, segments) => {
    expect(apiPathFor("GET", segments)).toBeNull();
  });

  it("refuses no path, too many segments and other methods", () => {
    expect(apiPathFor("GET", [])).toBeNull();
    expect(apiPathFor("GET", undefined)).toBeNull();
    expect(apiPathFor("GET", Array.from({ length: 13 }, () => "a"))).toBeNull();
    expect(apiPathFor("OPTIONS", ["portfolios"])).toBeNull();
    expect(apiPathFor("TRACE", ["portfolios"])).toBeNull();
    expect(apiPathFor("get", ["portfolios"])).toBeNull();
  });
});
