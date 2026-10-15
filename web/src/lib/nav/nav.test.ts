import { describe, expect, it } from "vitest";

import { activeItem, findNavItem, MOBILE_EXCEPTIONS, MOBILE_ROUTES, NAV, visibleNav } from "./nav";

const all = NAV.flatMap((g) => g.items);

describe("navigation", () => {
  it("answers every mobile route with a web route or a recorded exception", () => {
    const mapped = new Set(all.flatMap((i) => i.mobile));
    for (const route of MOBILE_ROUTES) {
      expect(mapped.has(route) || route in MOBILE_EXCEPTIONS, route).toBe(true);
    }
    for (const route of mapped) expect(MOBILE_ROUTES, route).toContain(route);
  });

  it("has unique hrefs, each naming its task", () => {
    expect(new Set(all.map((i) => i.href)).size).toBe(all.length);
    for (const item of all) expect(item.task).toMatch(/^P14-T\d\d$/);
  });

  it("shows forex only when the server enables it and operator views only to support", () => {
    const ids = (c: { forex: boolean; support: boolean }) => visibleNav(c).map((g) => g.id);
    expect(ids({ forex: false, support: false })).not.toContain("forex");
    expect(ids({ forex: false, support: false })).not.toContain("operator");
    expect(ids({ forex: true, support: false })).toContain("forex");
    expect(ids({ forex: false, support: true })).toContain("operator");
    expect(visibleNav({ forex: false, support: false }).flatMap((g) => g.items.map((i) => i.href))).not.toContain("/forex");
  });

  it("finds items and marks the longest matching prefix active", () => {
    expect(findNavItem("/goals")?.label).toBe("Goals");
    expect(findNavItem("/nope")).toBeUndefined();
    expect(activeItem("/portfolio/transactions/abc", all)?.href).toBe("/portfolio/transactions");
    expect(activeItem("/portfolio", all)?.href).toBe("/portfolio");
    expect(activeItem("/portfolios-x", all)).toBeUndefined();
  });
});
