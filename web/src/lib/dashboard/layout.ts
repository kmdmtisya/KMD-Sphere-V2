/**
 * The dashboard's section order and visibility (P14-T07.4, DEC-35). The same preference the mobile
 * Home uses (`dashboard_layout` in /me/preferences), so a layout set on one channel shows on the
 * other. Pure functions: no I/O.
 */
export const SECTIONS = ["wealthSummary", "metrics", "insight", "goals"] as const;
export type Section = (typeof SECTIONS)[number];
export type Layout = { order: Section[]; hidden: Section[] };

export const SECTION_LABELS: Record<Section, string> = {
  wealthSummary: "Wealth summary",
  metrics: "Key figures and activity",
  insight: "Portfolio Doctor insights",
  goals: "Goals",
};

export const DEFAULT_LAYOUT: Layout = { order: [...SECTIONS], hidden: [] };

const isSection = (value: unknown): value is Section => (SECTIONS as readonly unknown[]).includes(value);

/** A complete layout from a saved one: unknown names dropped, missing sections appended in default order. */
export function normaliseLayout(saved: { order?: unknown[]; hidden?: unknown[] } | null | undefined): Layout {
  const order = (saved?.order ?? []).filter(isSection).filter((s, i, all) => all.indexOf(s) === i);
  for (const s of SECTIONS) if (!order.includes(s)) order.push(s);
  const hidden = (saved?.hidden ?? []).filter(isSection).filter((s, i, all) => all.indexOf(s) === i);
  return { order, hidden };
}

export function visibleSections(layout: Layout): Section[] {
  return layout.order.filter((s) => !layout.hidden.includes(s));
}

/** Moves a section one place up (-1) or down (+1); at the edge nothing changes. */
export function moveSection(layout: Layout, section: Section, delta: -1 | 1): Layout {
  const i = layout.order.indexOf(section);
  const j = i + delta;
  if (i < 0 || j < 0 || j >= layout.order.length) return layout;
  const order = [...layout.order];
  [order[i], order[j]] = [order[j], order[i]];
  return { ...layout, order };
}

export function toggleSection(layout: Layout, section: Section): Layout {
  const hidden = layout.hidden.includes(section) ? layout.hidden.filter((s) => s !== section) : [...layout.hidden, section];
  return { ...layout, hidden };
}
