# WealthSphere — UI Execution Plan (Design System → Priority Screens)

> **Status: supplementary reference.** The authoritative roadmap is `EXECUTION_PLAN.md` (repo root); its tasks cite the steps below via `Ref` and Appendix B maps Step N to task IDs. Progress is tracked only in `TASK_CHECKLIST.md`. Where this file and `EXECUTION_PLAN.md` differ, the latter wins.

Scope: **UX delivery gates 1 and 2** from the UI/UX Design Specification (v1.1):

1. Shared Flutter design system: tokens, themes, typography, components, charts, navigation shell.
2. High-fidelity **Home Dashboard, Portfolio Overview, Compounding Calculator, Wealth Forecast, AI Wealth Copilot**, using typed fixtures that are clearly labelled `DEMO`.

Out of scope here: the remaining eight screens (gate 3), the backend/API connection (gate 4), and store release QA (gate 5). The last section lists how this plan hands over to them.

Sources analysed: `CLAUDE.md`, `SOLUTION_INTENT.md`, `WEALTHSPHERE_PROJECT_BRIEF.md`, `WEALTHSPHERE_CLAUDE_CODE_IMPLEMENTATION_GUIDE.md`, `WealthSphere_Project_Brief_UIUX_Updated.pdf` (Appendix A has the concept board on page 8). The UI/UX section is the same in all three Markdown files; treat `SOLUTION_INTENT.md` as the canonical copy.

---

## How to run each step

Each step is sized for one Claude Code session and one commit. Paste the following, replacing `N`:

```text
Read CLAUDE.md, then docs/UI_EXECUTION_PLAN.md — the "Decisions", "Ground rules" and "Step N" sections.
Execute Step N only. Before coding: inspect the repo, list the files you will create or change, and state assumptions.
After coding: run dart format, flutter analyze and flutter test from mobile/wealthsphere_app; report the commands,
results, changed files and anything left open. Do not start Step N+1.
```

Then check the step's **Done when** list yourself and commit:

```bash
git add -A && git commit -m "ui: step N — <title>"
```

If a step fails review, fix it in the same session before moving on. Later steps assume earlier ones are complete.

---

## Decisions and conflicts found in the docs

These are recorded as ADRs in Step 0. `CLAUDE.md` requires conflicts to be documented explicitly.

| # | Finding | Decision |
|---|---|---|
| D1 | `CLAUDE.md` / guide §22 order starts with Repository → Identity → DB schema and puts the dashboard at step 7. This plan builds UI first. | Allowed by UX gates 1–2, which explicitly use mock data with a `DEMO` indicator. Record as **ADR-0001**. All data goes through repository interfaces, so gate 4 swaps implementations without touching screens. |
| D2 | The concept board's bottom nav reads **Home / Portfolio / Invest / AI / More**. The written spec says **Home / Portfolio / AI Wealth / Goals / More**. | Follow the **written spec**, since the board is "inspirational, not a strict source". Holdings ("Invest") is reached from Portfolio. Calculator lives under More, as in the brief §3.2. Record as **ADR-0002**. |
| D3 | The Calculator and Forecast screens need numbers, but "Flutter must not become the source of financial truth" and "financial calculations must not depend on" the client. | **Default (A):** the demo `ForecastRepository` returns **canned fixture responses**. If the user changes inputs, the Forecast screen shows a clear DEMO notice that the projection is a sample for the default inputs. **No compounding math in Dart.** **Option (B):** before Step 12, build the backend forecast engine (guide §18 prompt) as a small FastAPI module with no DB, then point the repository at it. Choose at Step 12; A keeps this plan UI-only. |
| D4 | "No binary floating point for money" applies to the client too. | Money is `Decimal` (package `decimal`) plus an ISO currency code, and travels as **strings** in JSON. `double` is allowed **only** at the chart rendering boundary, for plotting coordinates. Record as **ADR-0003**. |
| D5 | Several brand tokens **fail WCAG AA (4.5:1) as text**, as measured below. | Brand colours stay as fills/accents, and Step 2 derives **text-safe semantic tokens**. A unit test enforces the contrast ratios. |
| D6 | The concept board shows a **Buy** button on Investment Details. | Do not build trade-execution affordances. Screen 7 is gate 3 anyway; "Watch"/"Research" only. |
| D7 | iOS cannot be built on this Windows machine. | CI gets a `macos` job running `flutter build ios --no-codesign` (Step 1). Device QA on iPhone needs a Mac or a cloud device service at Step 15. |
| D8 | `CLAUDE.md` sits in `docs/`. Claude Code always loads it from the **repo root**. | Move it to the root in Step 0, and update its reading-order paths to `docs/...`. |
| D9 | Guide §16 lists Dio, secure storage and local_auth for the app shell. | Defer them until the auth and backend steps. The guide also says to "avoid unnecessary dependencies", and none of these packages is used in gates 1–2. |

**Measured contrast (WCAG 2.x):**

| Pair | Ratio | Verdict |
|---|---|---|
| Teal `#0D9488` on white | 3.74 | Fails for body text; OK for large text and icons |
| Teal-700 `#0F766E` on white | 5.47 | Use for positive **text** in light mode |
| Gold `#F2B84B` on white | 1.79 | Never use as text on light backgrounds; fill/accent only (navy on gold = 8.18) |
| Muted `#64748B` on white / on `#F5F7FA` | 4.76 / **4.43** | Fails on the subtle background; use `#475569` there (7.06) |
| Blue `#2563EB` on white; white on blue | 5.17 | OK |
| Danger `#DC2626` on white / on `#F5F7FA` | 4.83 / 4.50 | Borderline OK |
| On navy `#102A43`: blue / danger / muted / teal | 2.83 / 3.03 / 3.08 / 3.91 | **All fail.** Dark mode needs lighter variants |
| On navy `#102A43`: `#60A5FA` / `#F87171` / `#2DD4BF` / `#94A3B8` / gold | 5.76 / 5.29 / 7.87 / 5.71 / 8.18 | Good dark-mode starting candidates |
| On `#1B3A5C` (elevated dark surface): `#F87171` | 4.20 | Fails. Keep elevated dark surfaces close to navy, or adjust |

---

## Ground rules (apply to every step)

- **Location:** monorepo root = this folder. App at `mobile/wealthsphere_app`. Do not create an extra `wealthsphere/` wrapper folder.
- **Stack:** Flutter stable (3.47.x locally) · Riverpod 3 (`Notifier`/`AsyncNotifier`, no `riverpod_generator`) · GoRouter · Freezed + json_serializable · `decimal` · `intl` · `fl_chart` (open-source; avoids the Syncfusion licence) · `shared_preferences` (UI preferences only) · `flutter_localizations` + gen-l10n.
- **Pin versions with `flutter pub add`**, never by guessing.
- **No hard-coded colours, spacing or radii in widgets.** Read them from `Theme.of(context)`, `context.wealthColors` and the token constants. A guard test (Step 2) fails the build on `Color(0x` outside `tokens/`.
- **RTL-ready:** use `EdgeInsetsDirectional`/`AlignmentDirectional`/`TextAlign.start`. The guard test also flags `EdgeInsets.only(left:`/`right:`.
- **All user-facing strings go in `lib/l10n/app_en.arb`** from the first screen onward. Retrofitting later is expensive.
- **Never use colour alone:** gains and losses always pair colour with a sign, an arrow icon and screen-reader text ("up 6.32 percent").
- **Accessibility:** touch targets ≥ 48 dp; every interactive element has a semantic label; text scale up to 2.0 without overflow; respect `MediaQuery.disableAnimationsOf` (reduced motion).
- **DEMO honesty:** every screen that shows fixture data shows a `DemoBadge`. No fixed investment-advice copy in UI code. AI and insight text comes from fixtures carrying `data_as_of` and sources.
- **No financial math in Flutter.** Display formatting and rounding are fine; deriving totals, returns, projections or allocation percentages is not.
- **Folder conventions:**

```text
mobile/wealthsphere_app/
├── lib/
│   ├── main.dart
│   ├── app/                      # App widget, router, route names, shell
│   ├── core/                     # config, data-source mode, l10n wiring, preferences storage
│   ├── l10n/                     # app_en.arb (+ generated)
│   ├── shared/
│   │   └── design_system/
│   │       ├── tokens/           # brand palette, semantic colours, spacing, radii, motion, breakpoints
│   │       ├── theme/            # AppTheme, ThemeExtensions, typography, ThemeModeController
│   │       ├── formatting/       # Money, MoneyFormatter, PercentFormatter, date labels
│   │       ├── components/       # the shared widget library
│   │       └── charts/           # chart widgets + ChartSemantics
│   └── features/
│       ├── dashboard/  portfolios/  calculator/  ai_wealth/  goals/  more/
│       │   └── {domain, data, presentation}/
├── assets/demo/                  # JSON fixtures, every file has "demo": true
├── test/                         # mirrors lib/
└── integration_test/
```

---

# Phase 0 — Repository foundation

## Step 0 — Repository bootstrap and ADRs

**Goal:** a versioned repo with the decisions above recorded before any code is written.

Build:
- `git init`, plus a root `.gitignore` (Flutter, Dart, IDE, `.env`) and a short root `README.md`.
- Move `docs/CLAUDE.md` → `CLAUDE.md` (root). Update its "Required Reading Order" paths to `docs/SOLUTION_INTENT.md` and the others. Add one line pointing to this plan.
- Extract the concept board from page 8 of `docs/WealthSphere_Project_Brief_UIUX_Updated.pdf` to `docs/design/wealthsphere-ui-concept.png`, as the spec requires. Use a throwaway script in a temp folder; do not add the tool to the repo.
- Create `docs/adr/0001-ui-first-with-demo-data.md`, `0002-primary-navigation.md` and `0003-client-money-representation.md` from D1, D2 and D4. Use the format Context / Decision / Consequences.

**Done when:** `git log` shows the first commit; `CLAUDE.md` is at the root; the PNG opens; the three ADRs exist.

## Step 1 — Flutter app scaffold, tooling and CI

**Goal:** an empty app that builds for Android and iOS, with lints, l10n, test harness and CI in place.

Build:
- `flutter create --org <your reverse domain> --platforms android,ios --project-name wealthsphere_app mobile/wealthsphere_app`. Ask the user for the org ID.
- Add the dependencies from Ground rules. Dev deps: `build_runner`, `freezed`, `json_serializable`, `mocktail`, `integration_test` (sdk), `flutter_test`.
- `analysis_options.yaml`: `flutter_lints` plus stricter rules (`prefer_const_constructors`, `avoid_print`, `always_declare_return_types`, `prefer_final_locals`, `require_trailing_commas`, `unawaited_futures`).
- gen-l10n: `l10n.yaml`, `lib/l10n/app_en.arb` with the app title, and `generate: true`.
- `main.dart` → `ProviderScope` → `WealthSphereApp` (`MaterialApp.router` placeholder).
- `dart_test.yaml` defining a `golden` tag (excluded locally by default; goldens are platform-sensitive, so CI ubuntu is the single golden platform).
- `test/helpers/pump_app.dart`: wraps a widget in ProviderScope, theme (light/dark param), localizations, `MediaQuery` (text scale param) and `Directionality` (RTL param). Every later widget test uses it.
- `.github/workflows/mobile.yml`: an **ubuntu** job (`flutter pub get`, `dart format --set-exit-if-changed`, `flutter analyze`, `flutter test`, including goldens) and a **macos** job (`flutter build ios --no-codesign`), triggered on paths `mobile/**`.
- Local prerequisite: `flutter doctor` currently shows `[!]` for the Android toolchain. Run `flutter doctor --android-licenses` and make sure an emulator boots, because Step 15 needs one.

**Done when:** `flutter analyze` is clean, `flutter test` passes, and `flutter run` on an Android emulator shows a blank themed app.

---

# Phase 1 — Shared design system (UX gate 1)

## Step 2 — Design tokens

**Goal:** a single source of truth for colour, spacing, shape, motion and breakpoints, with tested contrast.

Build in `shared/design_system/tokens/`:
- `brand_palette.dart`: the eight raw brand values from the spec, plus the derived shades needed for D5 (teal-700, slate-600, and dark-mode candidates). This is the only file allowed to contain `Color(0x…)`.
- `wealth_colors.dart`: a `ThemeExtension<WealthColors>` with **semantic** roles:
  - `positive`, `positiveText`, `negative`, `negativeText`, `warning`, `accent` (gold), `onAccent`
  - `surfaceSubtle`, `textPrimary`, `textMuted`
  - `riskLow`, `riskMedium`, `riskHigh`
  - `chartSeries` (≥ 6 colours, distinguishable in both themes), `chartContributions`, `chartGrowth`
  - `demoBadge`, `staleBanner`

  Provide `light` and `dark` instances, with `lerp` and `copyWith` implemented.
- `spacing.dart` (8-pt grid: 4, 8, 12, 16, 24, 32, 40, 48), `radii.dart` (12, 16, 20), `elevation.dart`, `motion.dart` (durations/curves plus a helper returning `Duration.zero` when reduced motion is on), `breakpoints.dart` (compact < 600, medium 600–839, expanded ≥ 840; phones only for now, so content is max-width-constrained on medium and above).
- `BuildContext` extension: `context.wealthColors`, `context.spacing`.

Tests:
- **Contrast test:** for both themes, assert ≥ 4.5:1 for every text-on-surface pair (`textPrimary`, `textMuted`, `positiveText`, `negativeText`, and the primary text on the primary colour) and ≥ 3:1 for icons and chart strokes. Compute it with `Color.computeLuminance()`.
- **Guard test:** scan `lib/` and fail on `Color(0x` outside `tokens/`, and on `EdgeInsets.only(left:` / `right:` and `TextAlign.left` / `right` anywhere.

**Done when:** both tests pass, and the contrast test fails if you temporarily set `textMuted` back to `#64748B` on the subtle background (proves it works; then revert).

## Step 3 — Themes, typography and theme switching

**Goal:** complete light and dark Material 3 themes that feel native on both platforms.

Build in `shared/design_system/theme/`:
- `AppTheme.light()` / `AppTheme.dark()` build `ThemeData` (`useMaterial3: true`) from tokens. Include `ColorScheme` mapping (primary = blue, secondary = teal, tertiary = gold, error = danger, with dark variants from Step 2), `WealthColors` extension and component themes: `CardTheme` (radius 16, no heavy shadows), `FilledButton`/`OutlinedButton`/`TextButton` (min size 48), `ChipTheme`, `SegmentedButton`, `InputDecorationTheme` (filled, radius 12, visible error style), `NavigationBarTheme`, `AppBarTheme`, `BottomSheetTheme`, `SnackBarTheme`, `DividerTheme`.
- Typography uses the **platform font** (SF Pro on iOS, Roboto on Android via default `Typography`), with a named scale (`displayAmount`, `headline`, `title`, `body`, `label`, `caption`). `displayAmount` uses tabular figures (`FontFeature.tabularFigures()`) so numbers don't jitter.
- Page transitions: Cupertino on iOS (swipe-back), the Material default on Android.
- `ThemeModeController` (Riverpod `Notifier`): system/light/dark, persisted via `shared_preferences` behind a small `PreferencesStore` interface in `core/`.
- Golden tests load a bundled test font (`test/fonts/`) so CI goldens are deterministic.

Tests: both themes build; the extension is present; buttons meet the 48 dp minimum; the theme mode persists and restores.

**Done when:** the app switches light/dark/system at runtime (temporary toggle on the placeholder screen) and all tests pass.

## Step 4 — Formatting primitives, status labels and state widgets

**Goal:** the building blocks every screen needs for money, change, trust labelling and async states.

Build:
- `formatting/money.dart`: an immutable `Money(Decimal amount, String currencyCode)` with `fromJson` from a **string** amount.
- `formatting/money_formatter.dart`: locale-aware formatting with currency symbol and grouping, compact mode (`$1.9M`) and sign handling, **without converting to `double`**. Rounding is half away from zero to the currency's minor units, documented in ADR-0003. Add `percent_formatter.dart` and `date_labels.dart` (relative "as of 2 hours ago" and absolute).
- Components:
  - `CurrencyAmount`: amount, optional native-currency secondary line, semantics label in words.
  - `ChangeIndicator`: arrow icon, sign, value, colour, and semantics "up 8.42 percent year to date".
  - `RiskLabel`: low/medium/high with icon and text, never colour-only.
  - `DisclosurePanel`: expandable assumptions/disclaimer block; collapsed summary always visible.
  - `DemoBadge` / `DemoBanner`
  - `DataAsOfLabel`
  - `StaleDataBanner` / `OfflineBanner`
  - `SkeletonLoader`: shimmer, static when reduced motion is on; exposes a semantics "Loading".
  - `EmptyState`: icon, title, body, optional action.
  - `ErrorState`: message plus Retry button.
  - `AsyncValueView<T>`: maps Riverpod `AsyncValue` to skeleton, error with retry, empty or data.

Tests:
- Formatter unit tests: large values above 2^53, negatives, zero, .005 rounding, KES/AED/USD, compact thresholds.
- Widget tests per component in light and dark, at text scale 2.0 and in RTL.
- Semantics label assertions.

**Done when:** all formatter edge cases pass, and no component overflows at 2.0 text scale.

## Step 5 — Cards, selectors, rows and AI inputs

**Goal:** the composite components used by the five priority screens.

Build in `components/`. Each component takes plain view-models (no repositories or providers inside) so it is independently testable:
- `WealthSummaryCard`: label, `CurrencyAmount`, `ChangeIndicator`, optional period slot and chart slot, `DataAsOfLabel`.
- `MetricCard`: icon, label, value, optional sub-value and change; tappable with ripple; optional "ⓘ" definition tooltip.
- `PeriodSelector`: a `SegmentedButton` over a `ChartPeriod` enum (1W, 1M, 3M, 6M, YTD, 1Y, ALL); each screen passes the subset it supports. Selected state is exposed to semantics.
- `PortfolioSwitcher`: header button showing the current portfolio, which opens a modal bottom sheet listing portfolios plus "All portfolios (consolidated)" with value and currency.
- `InvestmentRow`: logo/initials avatar, symbol and name, value in base currency plus native-currency line, `ChangeIndicator`; whole-row semantics.
- `ScenarioCard`: scenario name, return assumption, final value, selectable (radio semantics, visible selected border **and** check icon).
- `EvidenceSourceChip`: source label, provider, `as of` time; tap opens a detail sheet. Never opens arbitrary URLs from content.
- `AIChatComposer`: multiline field, send button (disabled when empty or busy), stop button while streaming, keyboard-safe, max length with counter.
- **Deferred to gate 3** (not built now): `TransactionTile`, `GoalProgressCard`, `PortfolioHealthCard`, `OpportunityCard`.

Tests: interaction (tap, select, send/stop), semantics, text scale 2.0, RTL, both themes.

**Done when:** every component above has widget tests, and none reads a provider.

## Step 6 — Charts

**Goal:** accessible, currency-aware chart widgets on `fl_chart`.

Build in `charts/`:
- `ChartPoint(DateTime x, Decimal y)` and `ChartSeries(id, label, points, role)`. Convert to `double` **only inside** the chart widgets (ADR-0003).
- `ChartSemantics`: generates a text summary ("Portfolio value rose from $X to $Y over 1 year; high $H on <date>, low $L on <date>") from the supplied series, using the formatters. These are summary statistics of given points for screen readers, not financial calculations. Wrap each chart in `Semantics(label: summary, excludeSemantics: true)`, and add a "View as table" toggle that shows the points in a list.
- `PerformanceLineChart`: single series, gradient area, touch tooltip (date plus formatted amount), axis labels via formatters, loading (skeleton) and empty states.
- `AllocationDonutChart` plus `AllocationLegend`: slices use the `chartSeries` palette **and** a legend with labels and percentages (from data, not computed); tapping a slice or legend row highlights it; centre label slot.
- `ForecastComparisonChart`: up to 3 line series with the selected series emphasised and others muted and dashed (not colour-only); x = years; y in compact money; legend.
- All animations respect reduced motion.

Tests: renders with data, empty and single-point inputs; semantics summary text; tooltip shows formatted values; goldens (tag `golden`) for each chart in light and dark.

**Done when:** the charts render in the placeholder screen in both themes, and screen-reader summaries read correctly (check with TalkBack once).

## Step 7 — Navigation shell and `WealthBottomNav`

**Goal:** the five-tab app shell with stable tab state and correct back behaviour.

Build in `app/`:
- GoRouter with `StatefulShellRoute.indexedStack` and 5 branches: `/home`, `/portfolio`, `/ai`, `/goals`, `/more`.
- Nested routes (placeholders now, filled in Phase 2):
  - `/portfolio/holdings` (stub until gate 3)
  - `/more/calculator`
  - `/more/calculator/forecast`
  - `/ai?scope=portfolio:<id>|forecast:<id>|goal:<id>` (contextual AI entry)
  - `/goals` placeholder
  - `/more` list with Calculator enabled and other items shown as "Coming soon"
- `WealthBottomNav`: `NavigationBar` with icon and label for every tab and selected-state semantics; re-tapping the active tab pops it to its root.
- Android system back pops nested routes, then exits from a root tab. iOS swipe-back works on nested routes.
- Route names live in one `AppRoutes` class; there are no string paths in widgets.
- A deep-link-ready URL structure (push-notification wiring comes later).

Tests: tab switching preserves each branch's stack; back from nested returns to the tab root; re-tap pops to root; contextual `/ai?scope=` parses scope.

**Done when:** you can navigate every tab and nested placeholder on the emulator with system back behaving correctly.

## Step 8 — Component gallery, goldens and gate 1 review

**Goal:** prove the design system is complete before screens depend on it.

Build:
- A debug-only `/_gallery` route (guarded by `kDebugMode`, absent in release) that shows every component in all states (loading/empty/error/data), with toggles for theme, text scale (1.0/1.5/2.0) and RTL.
- Golden tests for each component in light and dark at 1.0 and 2.0 text scale, tagged `golden`.
- A short `docs/design/design-system.md` covering the token table (light and dark, with measured contrast), the component catalogue with usage rules, and the do/don't list (DEMO labelling, no colour-only signals, no financial math).

**Done when:** **(Gate 1 exit)** you have reviewed the gallery against `docs/design/wealthsphere-ui-concept.png` in both themes and at 2.0 text, CI is green, and you are happy with the visual language. Fix visual issues **now**; they multiply across screens later.

---

# Phase 2 — Priority screens with DEMO data (UX gate 2)

## Step 9 — Demo data layer

**Goal:** typed domain models and repositories mirroring the planned API (guide §8), with demo implementations.

Build:
- Freezed models whose JSON shape follows the planned endpoints, with money as strings:
  - `PortfolioRef`, `PortfolioSummary` (value, invested, P/L, return %, data_as_of)
  - `PerformanceSeries` (per period), `AllocationSlice` (label, value, weight % from the server)
  - `PerformanceMetrics` (total return, CAGR, dividend yield, volatility — all server-provided)
  - `HoldingSummary`, `NetWorthSummary`, `IncomeSummary`, `GoalsSummary`
  - `InsightSummary` (text, data_as_of, sources)
  - `CompoundForecastRequest`, `CompoundForecastResponse` (per scenario: nominal and real yearly series, final value nominal and real, total contributions, total growth; assumptions echo)
  - `ChatTurn`, `ChatEvent`, `AnswerSection` (`kind`: observed | calculated | assumption | interpretation), `EvidenceSource`
- Repository **interfaces** in each feature's `data/`: `DashboardRepository`, `PortfolioRepository`, `ForecastRepository`, `CopilotRepository` (returns `Stream<ChatEvent>`), `DashboardLayoutRepository`.
- `Demo*Repository` implementations load `assets/demo/*.json` (every file carries `"demo": true`). They take a configurable latency (default ~600 ms) and a **failure-injection switch** so error and retry states can be exercised in the gallery and tests.
- `dataSourceModeProvider` (`demo` only for now). When `demo`, `DemoBadge` renders app-wide in the app bar area.
- Fixtures:
  - Multi-currency: USD base, with holdings in USD, AED and KES, so native vs converted values show.
  - 3 portfolios plus consolidated.
  - Series for every `ChartPeriod`.
  - One canned forecast response for the default calculator inputs.
  - Scripted copilot conversations for each suggested question, plus one refusal and one failure script.
  - Figures may echo the concept board; they are illustrative.

Tests: every fixture parses; repositories honour latency and failure injection; JSON round-trips keep `Decimal` precision.

**Done when:** all fixtures load through the interfaces in tests, and no screen code exists yet.

## Step 10 — Home Dashboard (screen 3)

Build `features/dashboard/presentation/`:
- Header with greeting (name from fixture), DEMO badge and a notifications icon (inert).
- `WealthSummaryCard` showing total wealth, return and `PeriodSelector` (1W 1M 1Y ALL) with `PerformanceLineChart`.
- Card grid of `MetricCard`s: Portfolio value, Net worth, Monthly income, Goals ("3 on track"). Each card navigates to its tab or a placeholder.
- AI insight summary card: text, `DataAsOfLabel` and `EvidenceSourceChip`s **from the fixture**, plus an "Ask Wealth AI" button → `/ai`.
- **Personalised widgets:** a "Customise" action enters edit mode (reorder list plus visibility switches). Reordering is also available **without drag** via semantics custom actions "Move up/down", for screen-reader users. Persist via `DashboardLayoutRepository` (local now; `PATCH /me/preferences` at gate 4).
- Pull-to-refresh. Per-section loading/empty/error via `AsyncValueView`, so one failed card doesn't blank the page.

Tests: renders all sections from fixtures; period change swaps series; reorder and hide persist across restart; the error in one section is isolated with a working retry; text scale 2.0; dark mode.

**Done when:** the screen matches the concept board's intent in both themes, and customisation survives an app restart.

## Step 11 — Portfolio Overview (screen 4)

Build `features/portfolios/presentation/`:
- `PortfolioSwitcher` in the header; selection is held in a Riverpod provider and shared with Home and AI scope.
- Value, P/L (`ChangeIndicator`) and `PeriodSelector` (1M 3M 6M 1Y ALL) with `PerformanceLineChart`.
- `AllocationDonutChart` with legend; the centre shows the total.
- Performance metrics grid of `MetricCard`s: total return, CAGR (annualised), dividend yield, volatility. Each has an ⓘ definition; values come from the server/fixture.
- A top-holdings preview of 5 `InvestmentRow`s, plus "View all holdings" → `/portfolio/holdings` (stub until gate 3).
- An "Ask AI about this portfolio" action → `/ai?scope=portfolio:<id>`.
- Loading, empty ("No investments yet" with an add-investment CTA, disabled in demo) and error states.

Tests: switching portfolio refreshes all sections; consolidated view; donut and legend interaction; the contextual AI link carries scope; empty portfolio state.

**Done when:** you can switch between all 3 portfolios plus consolidated, and every section updates.

## Step 12 — Compounding Calculator (screen 9)

> **Decide D3 before starting.** The default (A) uses canned results. For (B), first run the guide §18 forecast-engine prompt as its own step and wire `LiveForecastRepository`.

Build `features/calculator/presentation/`:
- Inputs:
  - Initial investment and monthly contribution, as currency inputs with a locale-aware decimal `TextInputFormatter` and a numeric keyboard.
  - Expected annual return (base, %), investment period (years), contribution growth (optional, %).
  - **Advanced options** (expandable): inflation %, annual fee %, compounding frequency, contribution frequency, and conservative/growth return rates (defaults 5% / 8% / 12%, labelled "Your assumptions").
- Validation from a single `ForecastInputLimits` definition that mirrors the future API schema. Messages are inline and human-readable; negative return rates are allowed within limits, with a note.
- "Calculate" calls `ForecastRepository.compound(request)` and shows a loading state on the button; on success it navigates to the Forecast screen with the response. Input state survives navigating back.
- Keyboard: next/done actions, the focused field scrolls into view, nothing is hidden behind the keyboard on small phones.
- A persistent footnote: projections are illustrative and not guaranteed.

Tests: validation boundaries; decimal input in en and a comma-decimal locale; submit builds the correct request (string amounts); loading and error states; layout at text scale 2.0 with the keyboard open (simulate the view inset).

**Done when:** a full happy path to Forecast works on the emulator, and invalid inputs can't be submitted.

## Step 13 — Wealth Forecast (screen 10)

Build `features/calculator/presentation/forecast/`:
- Three `ScenarioCard`s (Conservative / Base / Growth) showing rate and final value; tapping one selects it and updates everything below.
- `ForecastComparisonChart` with all three series, the selected one emphasised.
- Final value (`CurrencyAmount`), plus a **contributions vs growth** stacked bar with both amounts as text (non-colour-only) from the response.
- **Nominal / Real** `SegmentedButton`: switches between the response's nominal and inflation-adjusted series and values. No client-side inflation math.
- An assumptions `DisclosurePanel` echoing every input, inflation, fees and frequencies, plus "Projections are not guaranteed", prominent and collapsed-but-visible by default.
- In demo mode with non-default inputs: a DEMO notice that this is a sample projection for default inputs.
- Actions: "Edit assumptions" (back to the Calculator) and "Ask AI about this forecast" → `/ai?scope=forecast:<id>`.

Tests: scenario selection updates chart, values and semantics; the nominal/real toggle swaps to the response's real values; assumptions panel content; demo-mismatch notice logic; text scale 2.0.

**Done when:** every number on screen traces to a field in `CompoundForecastResponse` (spot-check against the fixture).

## Step 14 — AI Wealth Copilot (screen 6)

Build `features/ai_wealth/presentation/`:
- **Empty state:** intro, a DEMO notice ("Demo responses, not connected to your data") and suggested-question chips from the fixture.
- **Scope chip** above the composer: "All portfolios", a specific portfolio, a forecast or a goal (from `?scope=`). The user can change or remove it, and the scope is sent with each request (the server enforces authorisation at gate 4).
- **Thread:** user bubbles; the assistant message renders the **four labelled sections** (Observed data · Calculated · Assumptions · AI interpretation), then `EvidenceSourceChip`s and a `DataAsOfLabel`. Tool-progress rows come from events ("Fetching portfolio summary…").
- **Streaming:** consume `Stream<ChatEvent>` (token chunks, tool events, done). Use a stop button; announce completion to screen readers via `SemanticsService.announce`, not every token.
- **States:**
  - **Refusal** (fixture: cross-user request, or "guarantee me a return"): a distinct style explaining why.
  - **Failure:** the message stays with an inline Retry.
  - **Offline:** a banner; the composer is disabled.
- Questions outside the demo scripts get a scripted "Demo mode can answer the suggested questions only" reply. **No hard-coded advice in Dart.**
- Conversation is held in memory only (no local persistence of financial chat in this phase).
- A persistent footer: informational only, not financial advice; no trades are executed.
- Leave a header slot for future Opportunities / Portfolio Doctor entries (gate 3); do not build them.

Tests: suggested question → streamed answer with all sections and sources; stop mid-stream; refusal rendering; failure and retry; scope set from route, changed and removed; composer disabled while streaming and when offline; semantics announcements.

**Done when:** all scripted conversations play correctly on the emulator, including refusal and retry.

## Step 15 — Gate 2 hardening: journeys, accessibility and device QA

**Goal:** prove the five screens hold up as a product, not just as widgets.

Build:
- `integration_test/` journeys, run on the Android emulator (`flutter test integration_test -d <id>`):
  1. Launch → visit all 5 tabs → state preserved.
  2. Home → customise → reorder and hide → restart → persisted.
  3. Portfolio → switch portfolio → change period → View all holdings → back.
  4. More → Calculator → invalid then valid input → Forecast → switch scenario → Real → Ask AI (scope carried).
  5. AI → suggested question → streamed answer → retry on the failure script.
- An automated accessibility sweep over each screen with `meetsGuideline(androidTapTargetGuideline)`, `iOSTapTargetGuideline`, `labeledTapTargetGuideline` and `textContrastGuideline`, in light and dark, at text scale 2.0 and in RTL.
- A manual QA checklist in `docs/design/qa-gate2.md`, recording results per device:
  - Devices: small Android (360×640), large Android, iPhone SE-size and Pro Max-size.
  - Checks: notch and safe areas, keyboard, TalkBack and VoiceOver walkthrough, dark mode, reduced motion, long strings (pseudo-locale), and a side-by-side comparison with the concept board.
  - iOS: CI `macos` build plus a Mac or cloud device for VoiceOver (D7).

**Done when:** **(Gate 2 exit)** all journeys pass, the accessibility sweep is clean, the QA checklist is filled in, and CI is green on both jobs.

---

## After this plan

| Next | Notes |
|---|---|
| Gate 3: remaining 8 screens | Build the deferred components first (`TransactionTile`, `GoalProgressCard`, `PortfolioHealthCard`, `OpportunityCard`), then screens 1, 2, 5, 7, 8, 11, 12, 13. On screen 7, Watch/Research only, no Buy (D6). Opportunity cards need risk, evidence, data-as-of and score explanation; "Simulate" pre-fills the Calculator with **marked assumptions**. |
| Backend Phase 0–2 | Follow guide §16–18 (foundation, portfolio core, forecast engine). The Freezed DTOs from Step 9 become the contract to reconcile against the generated OpenAPI. |
| Gate 4: go live | Add Dio, auth (OIDC + PKCE, secure storage, biometrics) and `Live*Repository` implementations. Flip `dataSourceModeProvider`; DEMO badges disappear only for live-backed data. |
| Gate 5 | Full Android/iOS accessibility QA and store readiness (OWASP MASVS review). |
