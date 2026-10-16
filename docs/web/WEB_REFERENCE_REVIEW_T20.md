# Reference review of the built screens (P14-T20.6)

**Status:** 2026-10-16. Review of the portal's key screens against the reference images (`docs/design/references/executive-wealth-dashboard.png`; the forex workspace reference belongs to P14-T24) and the written composition rules (DEC-39: adopt the references' composition, keep the shared WealthSphere tokens).

**Material:** 80 screenshots, eight key screens (Home, Portfolio, Analytics, Goals, Net worth, Calculator, Copilot, Settings) at 1440, 1280, 1024, 768 and 375 px in Light and Dark: `docs/design/screenshots/p14/after/P14-T20/` (`<screen>-<theme>-<width>.jpg`). Taken as Bob with the large demo book, so Home and Portfolio show unpriced custom assets as "stale" figures: the data is stress data, not a showcase. Earlier module sets are in the sibling `P14-T03`, `T06`, `T07`, `T08` and `T25` folders, and the "before" set in `before/`.

## What matches the reference

- The frame: a fixed left navigation with grouped items and an active marker, a slim top bar with search (Ctrl K), a content column of rounded cards on a quiet background.
- Cards: the same radius, spacing and hierarchy (muted title with an info hint, large figure with the minor part muted, change pill and "as of" line).
- The distribution pattern: a donut beside a legend with name, share and amount; a table alternative for every chart.
- The dark theme: deep navy surfaces, soft borders, the chart palette (tested in both themes).
- Responsive behaviour: the navigation collapses to icons and then to a drawer; cards stack at 375 px with no horizontal scrolling at any of the five widths.

## Deliberate differences (decided, not defects)

| Reference | Portal | Why |
|---|---|---|
| Violet accent | WealthSphere blue accent | DEC-39: one brand across channels |
| Market ticker strip and a balance bar in the header | Not built | Out of scope for the portal's first release; no market-data licence for a ticker |
| "Upgrade" and promotional cards | None | No such product feature |
| Add Widget | Customise (show, hide, reorder) | Same purpose, saved to the account |
| Buy Asset button | None | The platform never places trades |
| Screenshot and full-screen buttons on charts | Table alternative button | Accessibility requirement |

## Remaining visual inconsistencies (for the user to close or accept: QG-35.5)

| # | Where | What | Suggested action |
|---|---|---|---|
| 1 | Home | The reference shows a multi-series investment chart and a profit-by-period bar chart. Home now has a net-worth line, but there is no profit-by-period series (the backend does not provide one) | Accept for now; add when a period-profit endpoint exists |
| 2 | All screens at 375 px | The top bar wraps to three rows (portfolio and currency selectors, status badge, icons), using about 140 px before the content | Fix by moving the selectors into the menu on narrow screens, or accept |
| 3 | Home, Portfolio | With unpriced assets the figures are marked stale; the demo data exaggerates this | Accept (it is the honest rendering of missing prices) |
| 4 | Charts | Tooltips and axis styling follow the reference in spirit; the reference's gradient bars are not used | Accept |

Closed during this review: Home had no wealth-over-time chart (added); chart axis labels could repeat (fixed); three layout shifts while loading (fixed, see the performance report).
