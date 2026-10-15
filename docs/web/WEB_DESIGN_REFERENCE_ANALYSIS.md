# Web portal: design reference analysis (P14, alias P14-UI-01 and P14-UI-02)

**Status:** Approved with the P14 plan change by the user on 2026-10-15. It is reviewed again at the web UX gate (P14-T03). DEC-39 was resolved on 2026-10-15: the shared WealthSphere palette is kept, and only the references' composition is adopted.

**Inputs:** the reference images in [docs/design/references](../design/references), the [web UI/UX specification](WEB_UI_UX_SPECIFICATION.md), the mobile design system (`mobile/wealthsphere_app/lib/shared/design_system`) and the project rules in CLAUDE.md.

## 1. Inventory

Every supported image (PNG, JPG, JPEG, WebP) in the folder was opened and inspected. There are two, both PNG; there are no JPG, JPEG or WebP files.

| File | Size | Committed | What it shows |
|---|---|---|---|
| `executive-wealth-dashboard.png` | 994 × 774 px | 2026-10-14 (commit 7068f11) | A browser-framed **dark** investment dashboard for a third-party concept product ("Chainx"): sidebar, top bar, ticker strip, KPI cards, a performance chart, a profits bar chart and an "AI robo-advisor" promotion |
| `forex-intelligence-workspace.png` | 1062 × 664 px | 2026-10-14 (commit 7068f11) | A **dark**, dense, multi-panel trading terminal: watchlist with sparklines, a candlestick chart with an indicator toolbar, positions and orders, an order ticket, an order book and a price ladder |

**Limits of the inspection:**
- Both images are about 1,000 px wide. Small labels are partly illegible (some ticker percentages, axis labels and ladder figures), so their exact values were not read. They are placeholders in any case.
- Neither image comes with a light-mode version, a mobile or tablet version, or a design file (Figma or similar). Spacing, type sizes and colours below are estimated from the pixels, not measured from a source file.

## 2. Image 1: executive wealth dashboard

**Layout**
- **Sidebar, about 190 px wide, collapsible:**
  - logo and collapse control at the top;
  - primary items: Dashboard (active, shown as a filled pill with an accent bar on the left), Market Summary, Portfolio (expandable to Stocks, Bonds and Mutual Funds), Analytics, Wallet, Community;
  - secondary items: Settings, Help & Support;
  - footer: an "Upgrade" promotion card and a binary **Dark Mode** switch.
- **Top area:**
  - a **ticker strip** (market status "The market is open", six stock symbols with logos, mini sparklines and coloured percentage changes);
  - a header row with a balance pill and three quick-action icon buttons (add, send, swap);
  - a search box with a `⌘K` hint, a notifications button and a profile button.
- **Page header:** title "Dashboard" with a greeting subtitle. On the right are actions: "Add Widget", a period selector ("All Time") and a primary "Buy Asset" button.
- **Grid:** two rows.
  - Row 1: a narrow "Total Assets" card (about 1/3) and a wide "Total Investments" chart card (about 2/3).
  - Row 2: a wide "Total Profits" chart card (about 2/3) and a promotion card (about 1/3).

**Components**
- **KPI card:**
  - an info icon beside the label;
  - a large figure with the **cents dimmed** ("$325,980" bright, ".65" muted);
  - a small rounded **change pill** (arrow and percentage), followed by "+$39,117.67 in this year" in muted text.
- **Distribution:**
  - a segmented horizontal bar in three tints of the accent;
  - a list underneath: dot, name, percentage below the name, and the amount right-aligned in tabular figures.
- **Performance chart:**
  - a line over thin vertical bars;
  - a dotted horizontal reference line;
  - a crosshair with a **dark tooltip card** (year, series dots and values);
  - years on the x-axis and abbreviated currency on the y-axis;
  - toolbar buttons for chart type (line or bars), screenshot and full screen.
- **Stacked bar chart:** value labels above each bar, a legend above the chart, and a full-screen button.
- **Promotion card:** an illustration with an icon, a headline, body text and a full-width secondary button.

**Visual language**
- **Surfaces:**
  - near-black base (about `#0B0B12`);
  - cards a step lighter (about `#15151F`);
  - 1 px low-contrast borders;
  - radius about 12 px for cards and 8 px for controls;
  - no visible drop shadows, so elevation comes from the border and a surface step.
- **Accent:** a single **violet** (about `#7C5CFF`) for the primary button, active states, chart series and focus. Lighter tints are used for the second and third series.
- **Status colours:** green for positive changes, red for negative.
- **Type:** a geometric sans; large semi-bold figures; muted grey secondary text. The card label is about 13 px and the figure about 28 to 32 px.
- **Spacing:** generous card padding (about 20 px) and gutters of about 16 px.

## 3. Image 2: forex trading workspace

**Layout**
- A full-screen workspace with an icon rail on the left and workspace tabs at the top ("Day-Traders", "Crypto Trading").
- Panels, each with its own title bar, icon buttons and instrument context line:
  - **Watchlist:** symbol, sparkline and badges, with Cryptos / My Watchlist tabs;
  - **Chart:** a drawing toolbar, indicator chips (MA, BOLL, VWAP, MACD) and an indicator menu;
  - **OHLC line and candles:** last-price labels on the price axis; range and interval selectors (1m, 5m, 30m, 1h, D, W, M);
  - **Positions / Orders:** status tabs (Working, Filled, Canceled, Pending, Partial) and a grid of symbol, side, quantity and filled quantity;
  - **Active Trade:** "Buy 100 @ASK" and "Sell 1 @BID" buttons, order settings, and "Cancel All" / "Close";
  - **Order Book (L2):** a depth chart over bid and ask columns;
  - **Ladder:** quantity, stop-loss and take-profit inputs, and a price ladder with bid and ask sizes.

**Visual language**
- **Colours:** a dark navy-black base (about `#0A0F1E`) with slightly lighter panel bodies; teal-green and red for bid/ask and up/down; an accent blue for selected tabs and toggles.
- **Density:** very compact. Text is about 10 to 11 px; rows are about 18 to 20 px; panels have hairline borders and almost no padding.

## 4. Common patterns (both images)

1. **Dark-first, layered surfaces:** a very dark base, slightly lighter cards or panels, hairline borders and no shadows.
2. **One accent colour** for primary actions and selection, with tints for related series.
3. **Card or panel with a title bar:** title (with an optional info icon) on the left, compact icon actions on the right (chart type, full screen, settings).
4. **Figures first:** large tabular numerals, with dimmed secondary parts (cents, units) and small change pills.
5. **Persistent navigation:** a left sidebar or icon rail, plus a top bar with search and account controls.
6. **Chart chrome:** muted gridlines, dark tooltip cards, inline legends and range or interval selectors.

## 5. Contradictions and conflicts, with the recommended approach

| # | Observation | Conflict | Recommendation |
|---|---|---|---|
| C1 | Image 1 uses a violet accent on near-black; the approved WealthSphere palette is navy, blue (`#2563EB` interactive), teal and gold, shared with mobile (QG-27.1: one token source) | Palette | **Keep the WealthSphere tokens** as the single source and adopt the references' **composition** (surface layering, borders, radii, figure styling, chart chrome). Violet (`violet600`/`violet400`) already exists as a chart-series token and stays a series colour. Changing the brand accent on every channel is a separate decision (**DEC-39**) |
| C2 | Both images are dark-only | Theme | The dark theme follows the references. The light theme is derived from the same token roles (mobile light palette) and is reviewed separately, with no reference image |
| C3 | Image 1 is dense but readable; image 2 uses 10 to 11 px text and low-contrast grey on navy | Accessibility (WCAG 2.2 AA, 1.4.3, 1.4.4) | Use image 1's density for the executive pages. For the forex workspace, take the panel structure from image 2 but **not its type size or contrast**: 13 px minimum for dense grids, 14 px body, every text pair measured at ≥ 4.5:1 |
| C4 | Up/down and bid/ask are shown by red and green only in image 2 (image 1 adds arrows) | "Colour is never the only signal" (spec §1.3) | Change pills always pair the sign, an arrow and text with the colour, as on mobile (`ChangeIndicator`) |
| C5 | "Buy Asset", quick buy/send/swap buttons, a wallet balance, the "Active Trade" ticket, order book and ladder | No trade execution (CLAUDE.md); no order affordance for real money (QG-28.9) | **Not built.** "+" maps to *Add transaction* (record keeping). The balance pill becomes the portfolio and reporting-currency selectors. The ticket exists only on the **paper-trading** page, always labelled PAPER TRADING (P13-T09 API). There is no order book or ladder: no level-2 data exists and none is licensed (DEC-19) |
| C6 | "Invest Smarter with Our AI Robo Advisor… personalised advice" | Not advice; AI output must separate facts, calculations, assumptions and interpretation | The slot becomes an **AI insights** card from the Copilot or Portfolio Doctor APIs, showing its structured sections, as-of time and the not-advice notice. No "robo-advisor" wording |
| C7 | A ticker strip of named stocks with company logos and "The market is open" | Market data needs provider evidence and licences; no equity streaming exists; third-party logos | No stock ticker. The strip's slot holds the **data-status chip** (FX and price freshness, from the API), as the spec's top bar already defines |
| C8 | "Chainx" logo and name, "Uxerflow" profile, "Upgrade / Unlock all features" promotion, "Community" | Third-party branding; no plans or community feature | Never copied. The WealthSphere logo and the user's display name are used; no promotional cards |
| C9 | A binary Dark Mode switch in the sidebar footer | Light / Dark / **System** is required (three options) | A three-option appearance control (see [WEB_THEME_SYSTEM.md](WEB_THEME_SYSTEM.md)) in the profile menu and on Settings › Appearance; a compact cycle button in the top bar |
| C10 | Crypto pairs and "Day-Traders / Crypto Trading" workspaces in image 2 | The forex universe is configured FX pairs; crypto is not in scope | Workspace tabs may become saved layouts; only the configured forex instruments appear, with their simulated or delayed labels |
| C11 | Placeholder figures ($325,980.65, 2018 to 2026 series, prices 141.42…) | Figures must come from the API or DEMO data | No figure from the images is reused. DEMO data is labelled DEMO, as on mobile |

## 6. Reference-to-screen mapping (P14-UI-02)

| Portal screen (task) | Reference | Taken from the reference | Adapted or excluded |
|---|---|---|---|
| Application shell (P14-T06) | Image 1 sidebar and top bar; image 2 icon rail | Collapsible sidebar with an active pill and accent bar, groups and a secondary section; top bar with `⌘K` search, notifications and profile; icon-rail collapsed state | Groups follow the spec (Overview, Portfolio, Planning, AI Wealth, Forex (flag), Account). There is no balance pill, quick-trade buttons or upgrade card. The theme control is three-state (C9) |
| Executive dashboard / Home (P14-T07) | Image 1 | Page header with greeting, period selector and "Customise" (for "Add Widget", DEC-35); KPI cards with dimmed decimals, change pill and period delta; wide performance chart with tooltip card and chart toolbar | Data from `/dashboard`, `/net-worth`, `/income/summary` and `/goals/summary`. The primary action is "Add transaction", not "Buy Asset". The promo slot becomes AI insights (C6) |
| Allocation (P14-T07, P14-T09) | Image 1 distribution card | Segmented bar plus a list with percentage and amount | Asset class, currency and country breakdowns from the API. Series use token colours with patterns or markers, not colour alone |
| Performance and profits charts (P14-T07, P14-T09) | Image 1 investments and profits charts | Line or area over bars, crosshair tooltip, value labels and legend, full-screen and screenshot buttons | TWR, XIRR and value series from analytics. The "screenshot" button becomes an image or CSV export of the visible data. Every chart has "view as table" |
| Net worth and income (P14-T11) | Image 1 KPI and bar-chart styling | Stacked bars per period with labels | Net-worth history from the new owner-scoped endpoint |
| AI insights and Copilot (P14-T12) | Image 1 promo card (position only) | A highlighted card with an icon and a single call to action ("Ask Copilot") | Structured answer sections, sources, as-of time and the not-advice notice |
| Forex live markets and workspace (P14-T13, P14-T24) | Image 2 | Multi-panel layout, panel title bars, watchlist with sparklines, candle chart with indicator chips, range and interval selectors, positions grid with status tabs | Paper-trading panels only, labelled PAPER TRADING. Data type and feed status are always shown. No order book, ladder or real order buttons (C5). Readable type size (C3) |
| Settings › Appearance (P14-T16) | Image 1 footer switch (position only) | Easy discovery | Three-option radio group (C9) |
| Notifications and profile (P14-T06, P14-T16) | Image 1 bell and profile button | Placement in the top bar | Notification centre and profile menu as in the spec |

## 7. Design decisions recorded here (for approval)

1. **References govern composition and visual language, not content.** Layout, surface layering, card anatomy, figure styling and chart chrome follow the references. Labels, figures, features and branding do not.
2. **The palette comes from the shared WealthSphere tokens.** If the user wants the references' violet as the brand accent, that changes mobile too and is decided as **DEC-39** before P14-T03.
3. **The dark theme is benchmarked against image 1.** Its surface steps are re-derived from the navy tokens (`navy950` base, `navy800` raised) and the contrast is measured. The light theme mirrors the mobile light palette.
4. **Executive density for most pages; the forex workspace is denser** but keeps the 13 px minimum and AA contrast.
5. **Excluded from the build:** every pattern listed in C5 to C8, C10 and C11.

## 8. Before-and-after screenshots

- **Before:** no web portal exists yet (there is no `web/` folder), so there is no "before" screenshot of the portal. The baseline is:
  - the two reference images above;
  - the current product, the mobile app on Android, at Home in light and dark (DEMO data, 2026-10-15), in [docs/design/screenshots/p14/before](../design/screenshots/p14/before).
- **After:** each P14 UI task captures its screens in light and dark at 1440, 1280, 1024, 768 and 375 px into `docs/design/screenshots/p14/after/<task>/`. A side-by-side sheet compares the dashboard and the forex workspace with images 1 and 2 (P14-T20.5 and QG-35).
