# Web portal: repository audit and requirements (P14-T01, WEB-01)

**Date:** 2026-10-15. **Evidence:** the repository at `main` 3b3c6b1, with P13 complete. This audit re-checks the [parity matrix](CROSS_PLATFORM_FEATURE_PARITY_MATRIX.md) baseline of 2026-10-14 (commit 23d0903) against the code as it is now, and records the constraints the web must respect. Nothing on the web is built yet: there is no `web/` folder.

## 1. Method (P14-T01.1, T01.2)

| Inventory | Source | Result |
|---|---|---|
| Mobile routes | `lib/app/app_routes.dart` and the `GoRoute` paths under `lib/app` | 27 named routes (including welcome, sign-in and the debug gallery) plus dynamic children (`:id`, `:symbol`, `pair/:instrument`, `add`, `edit`) |
| Mobile API use | Every `'/api/v1/…'` string in `lib/` (live repositories, `core/network`, account, alerts, notifications) | 45 path strings (about 40 distinct endpoints) across 17 files, plus the forex endpoints built from a base path in `live_forex_repository.dart` |
| Backend API | `backend/openapi.json` | 98 paths and 124 operations, plus the `WS /api/v1/forex/stream` WebSocket (not in OpenAPI) |
| Shared components | `lib/shared/design_system` (components, charts, theme, formatting) | 36 widgets (§5) |

## 2. Corrections to the matrix baseline (P14-T01.3)

The baseline marked some capabilities "Live" on mobile because the API exists. The app does not call these endpoints, so on mobile they are **API only, with no screen**:

| Row | Capability | Was | Now (evidence: no call in `lib/`) |
|---|---|---|---|
| 3 | Risk profile | Live | API only (`/risk-profiles`); no mobile screen |
| 5 | Portfolio archive | Live (with list, create, edit) | List, create, edit and summaries are live; **archive** is API only |
| 8 | Manual valuations | Live | API only (`/portfolios/{id}/valuations`) |
| 9 | Asset search, custom assets | Live | Asset classes, asset detail and prices are live; **catalogue search** and **custom assets** (`POST /assets`) are API only |
| 11 | Compounding calculator | `POST /forecasts/compound` | Live, but through `POST /forecasts/scenarios` (backend-calculated). `/forecasts/compound` is unused by the app |
| 13 | Goal contribution estimate | Live | Goals CRUD and progress are live; `POST /forecasts/goal` is API only |
| 14 | Liabilities | Live (CRUD) | Net worth is live; **liabilities CRUD** is API only |
| 16 | FX rates and history | Live | Currencies, preferences, convert, status and refresh are live; `/fx/rates` and `/fx/history` are API only |
| 19 | Opportunity runs, simulate | Live | Opportunities, runs and compare are live; **simulate** hands off to the calculator, and `POST /ai/simulate` is API only |
| 20 | Universe, scores, compatibility, research | Live in the instrument screens | API only (`/universe`, `/universe/scores`, `/universe/compatibility`, `/research`); the instrument screens use DEMO data |

**Consequence.** Parity (QG-28.2) means the web has what mobile has. The rows above are **web extensions on an existing API**: the plan already builds them in their web tasks, and they are recorded as extensions, not as parity.

## 3. Backend gap list (P14-T01.3)

There is no change from the baseline's section 2. These capabilities need backend work or a decision first:
- reports and exports (DEC-33, P14-T15);
- owner-scoped global search (P14-T07);
- net-worth history (P14-T11);
- layout and saved-view preferences (DEC-35);
- session management (P14-T16);
- operator endpoints (DEC-34, P14-T17);
- optimistic concurrency (P14-T18).

New since the baseline:

| Gap | Why | Task |
|---|---|---|
| A single-use WebSocket ticket for the forex stream | The stream authenticates with a bearer token today; the browser has no token (BFF) | P14-T13 (already planned) |
| No backend change for appearance | `theme_mode` already exists in `/me/preferences` | P14-T25 |
| The mobile app saves its appearance on the device only | One choice across devices needs the app to use `/me/preferences` | DEC-40, P14-T18 |

## 4. Constraints for the web (P14-T01.3)

| Constraint | Evidence | Effect on the web |
|---|---|---|
| **The API accepts bearer tokens only** | Every protected route verifies a Keycloak access token (docs/dev-setup.md "Backend authentication") | The browser never holds a token. The BFF keeps it server-side and forwards calls (DEC-31, P14-T05) |
| **CORS is off by default** | `cors_allowed_origins = []`; only explicit https origins are accepted (`app/core/config.py`) | The browser calls only the portal origin. The BFF calls the API server to server, so CORS stays off |
| **The forex stream is a WebSocket with a bearer token** | `stream_api.py` | It needs the single-use ticket minted by the BFF (P14-T13) |
| **Mobile plugins with no web equivalent** | `pubspec.yaml`: `flutter_secure_storage`, `flutter_appauth`, `local_auth`, `path_provider`, `cryptography` (encrypted snapshots), FCM/APNs device registration | No secure local storage, no biometrics, no offline snapshots and no push in web v1: matrix exceptions 23 and 24 |
| **Forex is refused outside local and test** | `Settings._forex_only_in_development` (P13-T14) | The web forex entry follows the server flag (QG-28.6), and production shows nothing until P17-T09 |
| **DEMO data is a client-side mode on mobile** | `WS_DATA_SOURCE=demo` (debug builds) | The web needs its own clearly labelled development fixtures. It must never present them as live (CLAUDE.md) |
| **Money is decimal strings** | ADR-0003, ADR-0006 | No number arithmetic on money in `web/` (lint guard, QG-26.3, QG-30.6) |

## 5. Component audit (P14-T01.7, alias P14-UI-03)

No web components exist. The web design system (P14-T03) mirrors the mobile ones, with the same names and meaning, styled from the reference visual language ([analysis](WEB_DESIGN_REFERENCE_ANALYSIS.md)):

| Mobile (Flutter) | Web equivalent (P14-T03) | Reference styling |
|---|---|---|
| `CurrencyAmount`, `ChangeIndicator`, `DataAsOfLabel`, `StaleChip`, `StaleDataBanner`, `DataQualityNotice` | Same names | Large tabular figure with a muted minor part; change pill with sign, arrow and text |
| `DemoBadge`, `DemoBanner`, `RiskLabel`, `DisclosurePanel`, `StatusBanner`, `OfflineBanner` | Same names (`SimulatedBadge`, `CalibrationBadge` added for forex) | — |
| `WealthCard`, `MetricCard`, `WealthSummaryCard` | `Card`, `KpiCard` | Card title bar with an info icon and compact actions; layered surface with a 1 px border |
| `PortfolioHealthCard`, `GoalProgressCard`, `ScenarioCard`, `OpportunityCard`, `InvestmentRow`, `TransactionTile` | Same names; `InvestmentRow` and `TransactionTile` become `DataGrid` rows on desktop and cards under 768 px | Distribution list with dot, name, percentage and right-aligned amount |
| `PerformanceLineChart`, `AllocationDonutChart` (+ `AllocationLegend`), `ForecastComparisonChart`, `ChartFrame`, chart semantics | Same names plus `WealthAreaChart` and `CandleChart`; every chart keeps the text summary and "view as table" | Crosshair tooltip card, muted grid, inline legend, toolbar (type, full screen, export) |
| `PeriodSelector`, `PortfolioSwitcher` | Segmented control; top-bar portfolio selector | Segmented control as in the references |
| `AIChatComposer`, `EvidenceSourceChip` | `ChatComposer`, `AnswerView`, `EvidenceSourceChip`, `ToolActivity` | — |
| `SkeletonLoader`, `SkeletonBox`, `EmptyState`, `ErrorState`, `LoadErrorView`, `AsyncValueView` | `Skeleton`, `EmptyState`, `ErrorState` (with correlation id and retry), async wrapper | — |
| `WealthBottomNav` | `Sidebar` (desktop), drawer (under 768 px) | Collapsible sidebar with an active pill and an accent bar |
| `ThemeModeController`, `AppTheme`, `WealthTypography` | Theme provider, generated CSS tokens, type scale (P14-T25, P14-T03) | Light, Dark and System ([WEB_THEME_SYSTEM.md](WEB_THEME_SYSTEM.md)) |

## 6. Design references (P14-T01.5, T01.6)

Both images in `docs/design/references` were inspected. The catalogue, the conflicts and the reference-to-screen mapping are in [WEB_DESIGN_REFERENCE_ANALYSIS.md](WEB_DESIGN_REFERENCE_ANALYSIS.md), approved with the P14 plan change on 2026-10-15.

## 7. Every mobile route mapped (acceptance check)

| Mobile route | Matrix row | Backend API |
|---|---|---|
| `/welcome`, `/sign-in` | 1 | Keycloak (PKCE); `GET /me` |
| `/home` | 4 | `/net-worth`, `/income/summary`, `/goals/summary`, `/me`, `/me/preferences` |
| `/portfolio` (`:id`, `edit`) | 5 | `/portfolios`, `/portfolios/{id}`, `/portfolios/{id}/summary`, `/portfolios/consolidated/summary`, `/allocation`, `/performance`, `/risk` |
| `/portfolio/holdings` (`:symbol`) | 6, 9 | `/portfolios/{id}/holdings`, `/assets/{id}`, `/assets/{id}/prices`, `/asset-classes` |
| `/portfolio/transactions`, `…/add` | 7 | `/portfolios/{id}/transactions`, `…/{tid}`, `…/{tid}/reversal` |
| `/ai` (scope parameter) | 17 | `POST /ai/chat`, `/ai/conversations` |
| `/ai/doctor` | 18 | `POST /ai/portfolio-doctor` |
| `/ai/opportunities`, `…/compare` | 19 | `POST /ai/opportunities`, `/ai/opportunities/runs`, `POST /ai/compare` |
| `/goals`, `/goals/add` (`:id`) | 13 | `/goals`, `/goals/{id}`, `/goals/{id}/progress` |
| `/more` | — | Navigation hub (no API) |
| `/more/net-worth` | 14 | `/net-worth` |
| `/more/income` | 15 | `/income/summary`, `/portfolios/{id}/income` |
| `/more/calculator`, `…/forecast` | 11, 12 | `POST /forecasts/scenarios` |
| `/more/converter` | 16 | `/currencies`, `/me/currency-preferences`, `POST /fx/convert`, `/fx/status`, `POST /fx/refresh` |
| `/more/alerts` | 21, 22 | `/watchlist`, `/alerts`, `/alerts/events`, `/alert-preferences` |
| `/more/settings` | 2 | `/me`, `PATCH /me/preferences`, `/me/currency-preferences` (appearance is device-only, §3) |
| `/more/forex` and `…/pair/:instrument`, `…/opportunities`, `…/risk`, `…/calendar`, `…/paper` | 25 | `/forex/*` and `WS /forex/stream` |
| (background) push registration | 23 | `/devices` |
| `/_gallery` | — | Debug only; the web has its own development gallery (P14-T03) |

Every live repository (`lib/features/*/data/live_*.dart`, plus account, alerts, notifications and the `core/network` catalogue helpers) is covered by the rows above.
