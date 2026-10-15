import { describe, expect, it } from "vitest";

import { dataStatus } from "./data-status";

describe("dataStatus", () => {
  it("takes the weakest status", () => {
    expect(dataStatus([{ status: "current" }, { status: "current" }]).kind).toBe("current");
    expect(dataStatus([{ status: "current" }, { status: "cached" }]).kind).toBe("delayed");
    expect(dataStatus([{ status: "cached" }, { status: "stale" }]).kind).toBe("stale");
    expect(dataStatus([{ status: "current" }, { status: "unavailable" }]).kind).toBe("stale");
  });
  it("is unknown without rates, never 'current'", () => {
    expect(dataStatus([]).kind).toBe("unknown");
    expect(dataStatus(undefined).kind).toBe("unknown");
  });
});
