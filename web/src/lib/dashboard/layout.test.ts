import { describe, expect, it } from "vitest";

import { DEFAULT_LAYOUT, moveSection, normaliseLayout, toggleSection, visibleSections } from "./layout";

describe("dashboard layout", () => {
  it("completes a partial or unknown saved layout", () => {
    expect(normaliseLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(normaliseLayout({ order: ["goals", "bogus", "goals"], hidden: ["metrics", "nope"] })).toEqual({
      order: ["goals", "wealthSummary", "metrics", "insight"],
      hidden: ["metrics"],
    });
  });

  it("moves sections and stops at the edges", () => {
    const moved = moveSection(DEFAULT_LAYOUT, "goals", -1);
    expect(moved.order).toEqual(["wealthSummary", "metrics", "goals", "insight"]);
    expect(moveSection(DEFAULT_LAYOUT, "wealthSummary", -1)).toBe(DEFAULT_LAYOUT);
    expect(moveSection(DEFAULT_LAYOUT, "goals", 1)).toBe(DEFAULT_LAYOUT);
  });

  it("hides and shows sections without losing their place", () => {
    const hidden = toggleSection(DEFAULT_LAYOUT, "insight");
    expect(visibleSections(hidden)).toEqual(["wealthSummary", "metrics", "goals"]);
    expect(hidden.order).toEqual(DEFAULT_LAYOUT.order);
    expect(visibleSections(toggleSection(hidden, "insight"))).toEqual(DEFAULT_LAYOUT.order);
  });
});
