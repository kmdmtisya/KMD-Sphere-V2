# WealthSphere design system

How the shared Flutter design system is built and used. Everything is in `mobile/wealthsphere_app/lib/shared/design_system/`. The reference visual is [wealthsphere-ui-concept.png](wealthsphere-ui-concept.png). The debug **component gallery** (More tab, "Component gallery (debug)", route `/_gallery`) shows every component in every state, with toggles for light/dark, text scale 1.0/1.5/2.0 and right-to-left.

## 1. Principles

- **Semantic tokens, never raw values.** Widgets use roles (`context.wealthColors.positiveText`, `AppSpacing.m`, `context.wealthText.title`). Raw colour literals are allowed only in `tokens/brand_palette.dart`; a guard test (`test/guards/style_guard_test.dart`) fails the build otherwise.
- **No financial maths in the UI.** Money is `Money(Decimal, currency)`. The app formats and displays; the backend calculates (ADR-0003). `double` appears only as chart plotting coordinates.
- **Never colour alone.** Gain/loss has an arrow and a sign; risk has an icon and words; selection has an icon and the word "Selected"; chart emphasis uses dashes as well as colour.
- **Accessible by default.** 48 dp targets, text scales to 2.0x without overflow, RTL-safe (`Directional` layout only), reduced motion respected, one spoken phrase per figure.
- **Honest data.** Mock data carries a DEMO label; figures can show how fresh they are; forecasts are worded as assumptions, never promised returns.

## 2. Colour tokens and measured contrast

Ratios are WCAG 2.x contrast against the card `surface` and the page `scaffold`, measured with `test/helpers/contrast.dart` (the helper the contrast tests use). Text roles must reach 4.5:1; icons, borders and chart strokes 3:1. The gold `accent` is a **fill with text on top**, never text or a thin stroke on a light surface (1.79:1 there). `divider` is decorative only.

### Light theme

| Role | Value | vs surface | vs scaffold |
|---|---|---|---|
| `primary` | #2563EB | 5.17 | 4.82 |
| `accent` | #F2B84B | 1.79 | 1.67 |
| `scaffold` | #F5F7FA | 1.07 | 1.00 |
| `surface` | #FFFFFF | 1.00 | 1.07 |
| `surfaceElevated` | #FFFFFF | 1.00 | 1.07 |
| `border` | #64748B | 4.76 | 4.43 |
| `divider` | #E2E8F0 | 1.23 | 1.15 |
| `textPrimary` | #102A43 | 14.64 | 13.64 |
| `textMuted` | #475569 | 7.58 | 7.06 |
| `positive` | #0D9488 | 3.74 | 3.49 |
| `positiveText` | #0F766E | 5.47 | 5.10 |
| `negative` | #DC2626 | 4.83 | 4.50 |
| `negativeText` | #B91C1C | 6.47 | 6.03 |
| `warningText` | #B45309 | 5.02 | 4.68 |
| `riskLow` | #0F766E | 5.47 | 5.10 |
| `riskMedium` | #B45309 | 5.02 | 4.68 |
| `riskHigh` | #B91C1C | 6.47 | 6.03 |
| `onPrimary/primary` | #FFFFFF | 5.17 | - |
| `chartSeries[0]` | #2563EB | 5.17 | 4.82 |
| `chartSeries[1]` | #0D9488 | 3.74 | 3.49 |
| `chartSeries[2]` | #B45309 | 5.02 | 4.68 |
| `chartSeries[3]` | #7C3AED | 5.70 | 5.31 |
| `chartSeries[4]` | #DB2777 | 4.60 | 4.28 |
| `chartSeries[5]` | #475569 | 7.58 | 7.06 |

### Dark theme

| Role | Value | vs surface | vs scaffold |
|---|---|---|---|
| `primary` | #60A5FA | 5.76 | 6.85 |
| `accent` | #F2B84B | 8.18 | 9.73 |
| `scaffold` | #0B1B2B | 1.19 | 1.00 |
| `surface` | #102A43 | 1.00 | 1.19 |
| `surfaceElevated` | #14304C | 1.09 | 1.29 |
| `border` | #7A8BA3 | 4.22 | 5.02 |
| `divider` | #14304C | 1.09 | 1.29 |
| `textPrimary` | #F1F5F9 | 13.37 | 15.90 |
| `textMuted` | #94A3B8 | 5.71 | 6.79 |
| `positive` | #2DD4BF | 7.87 | 9.36 |
| `positiveText` | #2DD4BF | 7.87 | 9.36 |
| `negative` | #F87171 | 5.29 | 6.30 |
| `negativeText` | #F87171 | 5.29 | 6.30 |
| `warningText` | #FBBF24 | 8.77 | 10.43 |
| `riskLow` | #2DD4BF | 7.87 | 9.36 |
| `riskMedium` | #FBBF24 | 8.77 | 10.43 |
| `riskHigh` | #F87171 | 5.29 | 6.30 |
| `onPrimary/primary` | #0B1B2B | 6.85 | - |
| `chartSeries[0]` | #60A5FA | 5.76 | 6.85 |
| `chartSeries[1]` | #2DD4BF | 7.87 | 9.36 |
| `chartSeries[2]` | #FBBF24 | 8.77 | 10.43 |
| `chartSeries[3]` | #A78BFA | 5.38 | 6.40 |
| `chartSeries[4]` | #F472B6 | 5.53 | 6.58 |
| `chartSeries[5]` | #CBD5E1 | 9.86 | 11.73 |


## 3. Spacing, shape, motion and sizing

| Token | Values |
|---|---|
| `AppSpacing` | xxs 4 · xs 8 · s 12 · m 16 · l 24 · xl 32 · xxl 40 · xxxl 48 |
| `AppRadii` | small 12 · medium 16 · large 20 |
| `AppElevation` | none 0 · low 1 · medium 3 · high 6 |
| `AppMotion` | fast 150 ms · standard 250 ms · slow 400 ms; `AppMotion.resolve` returns zero when the user has reduced motion on |
| `AppTouchTarget` | Android 48 dp · iOS 44 dp (48 is used everywhere) |
| `AppBreakpoints` | compact < 600 · medium ≥ 600 · expanded ≥ 840; content is capped at 640 dp |

Typography (`context.wealthText`): `displayAmount`, `amount` (tabular figures), `headline`, `title`, `body`, `label`, `caption`. The font is the platform's own and follows the system text-size setting.

## 4. Component catalogue

Import from `components/components.dart` and `charts/charts.dart`.

| Component | Use it for | Rules |
|---|---|---|
| `CurrencyAmount` | Any money value | Takes a `Money`; one spoken phrase ("minus 50.00 USD"); scales down instead of overflowing; optional native-currency line |
| `ChangeIndicator` | Gain, loss, unchanged | Arrow + sign + words; a value that rounds to zero is "unchanged" |
| `RiskLabel` | Low, medium, high risk | Distinct icon and words per level |
| `DisclosurePanel` | Assumptions, methodology | Summary always visible; details expand |
| `DemoBadge`, `DemoBanner` | Anything not from live data | Mandatory on mock data |
| `DataAsOfLabel` | Freshness of a figure | "As of 2 hours ago"; a date after a week; full timestamp on long-press |
| `OfflineBanner`, `StaleDataBanner` | Connectivity, old data | Live regions; the retry button drops below the message at large text |
| `SkeletonLoader`, `SkeletonBox` | Loading | One shimmer; static with reduced motion; announced as "Loading" |
| `EmptyState`, `ErrorState` | Nothing to show, failure | Friendly text and optional action; never show raw errors |
| `AsyncValueView` | Riverpod `AsyncValue` to UI | Existing data wins over a refresh error; error screen only when there is no data |
| `WealthSummaryCard`, `MetricCard`, `WealthCard` | Headline figures and tiles | Plain slots, no data fetching; optional definition tooltip |
| `PeriodSelector` | Chart range | `ChartPeriod` subset per screen; spoken long names |
| `PortfolioSwitcher` | Choose a portfolio or the consolidated view | `null` id means consolidated; values come from the backend |
| `InvestmentRow` | A holding in a list | Initials avatar only (no remote logos); one focus target |
| `ScenarioCard` | Conservative, Base, Growth | Radio semantics; the rate is worded as an assumption |
| `EvidenceSourceChip` | Source of a fact | Opens a detail sheet; never opens a URL |
| `AIChatComposer` | AI message input | Send disabled when blank or streaming; stop while streaming; length limit |
| `WealthBottomNav` | The five tabs | Labels always visible; re-tap returns to the tab root |
| `PerformanceLineChart` | Value over time | Tooltip with exact formatted value; table view; summary for screen readers |
| `AllocationDonutChart` + legend | Allocation | Percentages supplied by the backend; legend repeats label and percent |
| `ForecastComparisonChart` | Up to three scenarios | Selected line solid, others dashed |

## 5. Do and don't

**Do**
- Label mock data DEMO, and show data freshness where a figure can go stale.
- Pass `Money` and `Decimal` values straight from the backend model to the widget.
- Use `Directional` paddings and alignments, and test new widgets in light, dark, 2.0x text and RTL through `pumpApp`.
- Give every interactive element a 48 dp target and a spoken label.
- Add a new widget to `lib/app/gallery/gallery_sections.dart` so it is reviewed and golden-tested.

**Don't**
- Don't use `Color(0x...)`, `Colors.red` and the like outside `brand_palette.dart`.
- Don't use `double` or `num` for money, or add, convert or derive amounts in the UI.
- Don't rely on colour alone, and don't use left/right-specific layout APIs.
- Don't present forecasts or scenarios as guaranteed returns, or show content-supplied URLs as links.
- Don't let a design-system component read a repository or provider (view-models only).

## 6. Tests and goldens

- Every component has widget tests in light/dark, 1.0x/2.0x and LTR/RTL with no overflow, plus semantics assertions.
- Golden images (tag `golden`) live beside the tests in `goldens/`. They are authoritative on the CI Linux runner only and skip on other platforms. To refresh them, run `flutter test --update-goldens --tags golden` on Linux (or a temporary CI step) and review the images before committing.
- Gallery goldens cover each section (charts have their own) in light and dark at 1.0x and 2.0x.
