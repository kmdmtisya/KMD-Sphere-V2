# WealthSphere Web Portal: UI/UX specification

**Status:** Proposed (2026-10-14). It is reviewed at the web UX gate (P14-T03), as the mobile design system was at UX Gate 1. The mobile specification remains the [UI/UX Design Specification v1.1](../SOLUTION_INTENT.md#uiux-design-specification--approved-product-direction-v11). This document adds the desktop and web rules and changes no mobile behaviour. **Visual direction (proposed 2026-10-15):** the reference images in [docs/design/references](../design/references) govern the portal's composition and visual language, as analysed and mapped to screens in [WEB_DESIGN_REFERENCE_ANALYSIS.md](WEB_DESIGN_REFERENCE_ANALYSIS.md); their labels, figures, trading features and branding are not used.

## 1. Principles

1. **A workspace, not a stretched phone.** Desktop uses its width for multi-column dashboards, side-by-side analysis and dense tables, with phone layouts kept for narrow windows.
2. **The same truth and the same words.** Figures, as-of times, notices and labels come from the API. The web uses the same server-sent disclosures (not advice, DEMO, simulated, stale, requires calibration), and they are never shortened away.
3. **Colour is never the only signal.** Every gain, loss or status pairs colour with a sign (+ or −), an arrow or icon, and text.
4. **Keyboard first-class.** Everything reachable by mouse is reachable by keyboard, with a visible focus ring.
5. **Calm motion.** Transitions last 150 to 200 ms and are switched off under `prefers-reduced-motion`.

## 2. Tokens and theme

- **Source.** Brand and semantic tokens come from `design/tokens/wealthsphere.tokens.json`, generated into CSS variables, with the same values and measured contrast as the mobile `BrandPalette` and `WealthColors`:
  - brand: Midnight Navy `#102A43`, Emerald Teal `#0D9488`, Warm Gold `#F2B84B`;
  - text-safe shades: teal 700 `#0F766E`, red 700 `#B91C1C`, amber 700 `#B45309`;
  - dark-mode variants: navy 950 and 800, teal 400, red 400, amber 400.
- **Semantic roles:**
  - `--ws-positive`, `--ws-negative`, `--ws-neutral`;
  - `--ws-warning`, `--ws-critical`, `--ws-info`;
  - `--ws-surface`, `--ws-surface-raised`, `--ws-surface-sunken`;
  - `--ws-border`, `--ws-focus`, `--ws-text`, `--ws-text-muted`;
  - eight chart series (`--ws-series-1..8`), checked for 3:1 contrast against the surface and for colour-vision safety.
- **Themes.** Light, Dark and System (the default), stored as `theme_mode` in `/me/preferences` and mirrored in a cookie for a flash-free first paint. The design is in [WEB_THEME_SYSTEM.md](WEB_THEME_SYSTEM.md).
- **Visual language from the references** ([analysis](WEB_DESIGN_REFERENCE_ANALYSIS.md) §4, §7):
  - layered surfaces: a dark base, raised cards one step lighter, 1 px low-contrast borders and no heavy shadows;
  - card anatomy: a title bar with an optional info icon and compact icon actions on the right (chart type, full screen, export);
  - figures: large tabular numerals, the minor part (cents) in the muted text token, and a change pill (sign, arrow, text, colour) followed by the period delta;
  - chart chrome: muted gridlines, a crosshair with a tooltip card, an inline legend, and range selectors as a segmented control;
  - the palette stays the shared WealthSphere tokens (decision DEC-39).
- **Scales.** Spacing on a 4 px base (4 to 64). Radius 12 px for cards (the mobile `AppRadii.small` and the references) and 8 px for controls. Elevation uses borders plus one subtle shadow. Desktop density is a compact row height of 36 px for tables and 44 px for touch layouts.
- **Type.** System font stack (no web-font download) with tabular figures for amounts, a 14 px desktop body and a 16 px body below 768 px. Zoom to 200% and text spacing overrides must not lose content (WCAG 1.4.4, 1.4.12).
- **No hard-coded styles.** A lint rule forbids colour literals and raw pixel spacing outside the tokens, mirroring the Flutter style guard.

## 3. Application shell

```text
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ◧ WealthSphere   [Search  Ctrl+K]   Portfolio ▾   AED ▾   ● Data: current   🔔  ☾  ◉ │  top bar
├───────────────┬──────────────────────────────────────────────────────┬───────────────┤
│ OVERVIEW      │ Home / Wealth overview                     [Export ▾]│ AI Copilot  ✕ │
│  Home         │ ┌ Total wealth ┐ ┌ Net worth ┐ ┌ Income (12m) ┐     │ (optional     │
│ PORTFOLIO     │ └──────────────┘ └───────────┘ └──────────────┘     │  right panel, │
│  Portfolios   │ [Wealth over time — 1M 3M 1Y 5Y All]                 │  resizable)   │
│  Holdings     │ [Allocation]                 [Performance]           │               │
│  Transactions │ [Recent transactions — data grid]                    │               │
│  Analytics    │ [AI insights — facts · calculations · assumptions]   │               │
│ PLANNING      │                                                      │               │
│  Calculator   │                                                      │               │
│  Forecast     │                                                      │               │
│  Goals        │                                                      │               │
│  Net worth    │                                                      │               │
│  Income       │                                                      │               │
│  Currency     │                                                      │               │
│ AI WEALTH     │                                                      │               │
│  Copilot      │                                                      │               │
│  Doctor       │                                                      │               │
│  Opportunities│                                                      │               │
│ FOREX (flag)  │                                                      │               │
│ ACCOUNT       │                                                      │               │
│  Alerts       │                                                      │               │
│  Reports      │                                                      │               │
│  Settings     │                                                      │               │
└───────────────┴──────────────────────────────────────────────────────┴───────────────┘
```

**Sidebar**
- Groups map onto the five mobile tabs (ADR-0002): Home, Portfolio, AI Wealth, Goals (inside Planning) and More (Account). Every mobile destination therefore has one obvious web place.
- It collapses to icons (state remembered), and the active item is marked by a bar and `aria-current`, not by colour alone.
- **Forex** appears only when the server says the module is enabled (DEC-23). It carries a "Simulated data" badge while the provider is the simulated one.
- **Operator** views appear only for the `support` role (DEC-34), and the API enforces it.

**Top bar**
- Global search (`Ctrl/⌘+K`) across the user's own portfolios, assets, transactions, goals, reports and watchlist.
- Portfolio selector, "All portfolios" included.
- Reporting-currency selector: this is the global preference, so changing it re-renders every figure with the server's conversion (FXCUR).
- Market-data status chip: current, delayed or stale with its age, linking to FX status.
- Notification centre, an appearance button that cycles Light, Dark and System, and the profile menu (profile, security, sessions, the Appearance choice, sign out).

**Main workspace:** breadcrumb, page title, contextual filters (period, portfolio, asset class), then the content.

**Right panel (optional):**
- The AI Copilot docked beside any page and scoped to that page (as mobile's "Ask about this" scope), plus contextual explanations.
- It is resizable from 320 to 560 px, can be collapsed, and closes with `Esc`.

## 4. Responsive behaviour

| Width | Layout |
|---|---|
| 1280px and wider (desktop) | Sidebar expanded; 12-column grid; KPI rows of 3 or 4; side-by-side charts; full data grids; right panel docked |
| 768–1279px (laptop and tablet) | Sidebar collapsed to icons (expands as an overlay); 8 columns; KPI rows of 2; charts stacked; grids with fewer default columns; right panel as an overlay sheet |
| Under 768px (phone browser) | Top bar with a menu button; navigation in a drawer; one column; **tables become card lists** (not shrunken tables); touch targets at least 44 px; copilot full screen |

Every core workflow (sign in, view the dashboard, add a transaction, change the currency, ask the copilot) is tested at 1440, 1280, 1024, 768 and 375 px wide, in light and dark (QG-27, QG-36). There is no horizontal page scroll at any of these widths; only wide data grids scroll inside their own container, with the first column pinned.

## 5. Components (web design system, P14-T03)

Each mirrors a mobile component where one exists (`lib/shared/design_system`), with the same name and meaning:

| Group | Components |
|---|---|
| Figures | `CurrencyAmount` (decimal string, currency, sign, tabular), `ChangeIndicator` (sign, arrow, text, colour), `DataAsOfLabel`, `StaleChip`, `DemoBadge`, `SimulatedBadge`, `RiskLabel`, `CalibrationBadge` |
| Cards | `KpiCard`, `PortfolioHealthCard`, `GoalProgressCard`, `ScenarioCard`, `OpportunityCard` |
| Data | `DataGrid` (TanStack Table): sort, filter, server pagination, column resize, show and hide, saved views, keyboard cell navigation, CSV export of what is shown, with a card-list fallback under 768 px |
| Charts | `PerformanceLineChart`, `AllocationDonutChart`, `ForecastComparisonChart`, `WealthAreaChart`, `CandleChart` (forex). Every chart has a text summary, a "view as table" toggle and keyboard-focusable points |
| AI | `ChatComposer`, `AnswerView` (facts, calculations, assumptions, interpretation and sources as separate sections), `EvidenceSourceChip`, `ToolActivity` (which tools ran) |
| States | `Skeleton`, `EmptyState`, `ErrorState` (with correlation ID and retry), `OfflineBanner`, `PermissionDenied`, `StatusBanner`, `DisclosurePanel` |
| Shell | `Sidebar`, `TopBar`, `CommandPalette`, `NotificationCentre`, `RightPanel`, `Breadcrumbs` |

A component gallery route (`/_gallery`, development only), as on mobile, shows every component in light, dark and 200% zoom, and in RTL. Visual regression uses Playwright screenshots.

## 6. Key screens

The mobile behaviour is unchanged; these are the desktop forms.

- **Home (executive dashboard).**
  - KPI row: total wealth, invested capital, market value, net worth, unrealised and realised P/L, income.
  - Wealth-over-time chart.
  - Allocation and currency exposure.
  - Portfolio performance.
  - Goal progress.
  - Recent transactions (grid).
  - AI insights.
  - Every figure comes from `/dashboard`, `/net-worth`, `/income/summary` and `/goals/summary` in the reporting currency. Widgets can be reordered and hidden, and the layout is saved per user (DEC-35).
- **Portfolios.**
  - List with summary columns; a detail page with Holdings, Transactions, Valuations, Analytics and Income tabs.
  - Create, edit and archive.
  - Add a transaction in a side drawer (all types, with currency and FX as on mobile).
  - Reversals, not deletion: the ledger is append-only.
  - Asset search and custom assets.
- **AI Copilot.**
  - A full page with the conversation list on the left and the answer view on the right, plus the docked panel on every page.
  - The stream shows tool activity, then a structured answer with source chips and as-of times.
  - Uncertainty and the not-advice notice are always visible.
- **Doctor, Opportunities, Compare, Simulate.** Desktop layouts with comparison tables. Every opportunity card shows risks, assumptions, data freshness and evidence, and the no-trading notice.
- **Calculator, forecast, goals, net worth, income, currency.** Input form and results side by side on desktop; scenario tables next to charts; converter and rate status.
- **Forex workspace (live markets: P14-T13; advanced workspace: P14-T24).**
  - A multi-panel layout: watchlist, candle chart with indicators, quote panel with feed status, calendar, scanner and paper trading.
  - PAPER TRADING and simulated or delayed labels are always on.
  - There is no order button of any kind for real money.
- **Reports and exports (P14-T15).** A report catalogue: choose a report and period, preview it, then download PDF, CSV or XLSX generated by the backend, with as-of times and the currency on every file.
- **Settings.**
  - Profile, reporting currency, Appearance (Light, Dark, System), notifications and privacy.
  - Security: password and MFA through the Keycloak account console, and active sessions with "sign out other sessions".
  - Account deletion request: the P16 workflow, shown when available.

## 7. Accessibility (WCAG 2.2 AA)

- **Structure.** Semantic landmarks (header, nav, main, aside), one `h1` per page, a skip link, and the route title announced on navigation.
- **Focus.** Visible focus that is never obscured (2.4.11), at least 24×24 px targets (2.5.8), and no drag-only interaction (2.5.7): widget reordering also has buttons.
- **Tables and charts.**
  - Tables use real `<table>` semantics, or the grid pattern with roving tabindex.
  - Sort state uses `aria-sort`.
  - Charts carry a summary sentence and a table alternative, and their series patterns or markers don't rely on colour.
- **Live regions.** Streamed AI text is announced politely, in chunks; feed-status changes are announced.
- **Checks.** axe-core in component and e2e tests (zero serious or critical violations); manual NVDA (Windows) and VoiceOver (macOS) read-throughs of the key journeys before the UX gate.

## 8. Keyboard shortcuts

| Keys | Action |
|---|---|
| `Ctrl/⌘+K` | Search and command palette |
| `G` then `H`, `P`, `A`, `G` | Go to Home, Portfolios, AI, Goals |
| `N` then `T` | New transaction (in a portfolio) |
| `/` | Focus the page filter |
| `Ctrl/⌘+J` | Toggle the copilot panel |
| `Esc` | Close the panel, drawer or dialog |

Shortcuts are listed in a help dialog (`?`), and can be turned off where they would conflict with assistive technology (WCAG 2.1.4).
