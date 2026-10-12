# Mobile DTOs and the API: field mapping

Generated from `dto-mapping.json` by `scripts/dto_mapping.py`; edit the JSON, not this file. Decision on client generation: [ADR-0013](../adr/0013-api-client-dtos.md).

Mobile DTOs (P03-T01, DEMO fixtures) against the API (P05). Statuses: same, renamed (the API name differs), dto-only (the API has no such field yet), api-only (the DTO does not read it yet). Every difference names its resolution and the task that owns it. Checked by backend/tests/test_dto_mapping.py; docs/contracts/dto-mapping.md is generated from this file by scripts/dto_mapping.py.

## Endpoints that exist

### PortfolioRef - `GET /api/v1/portfolios` (PortfolioOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `id` | `id` | same |  |  |
| `name` | `name` | same |  |  |
| `base_currency` | `base_currency` | same |  |  |
| - | `portfolio_type` | api-only | Read in P07-T08 (settings) when portfolios can be edited in the app. | P07-T08 |
| - | `archived_at` | api-only | The list hides archived portfolios by default; the DTO adds it with the archive flow. | P07-T08 |

The DEMO pseudo-id `consolidated` matches GET /api/v1/portfolios/consolidated/summary.

### PortfolioSummary - `GET /api/v1/portfolios/{portfolio_id}/summary` (SummaryOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `portfolio_id` | `portfolio_ids` | renamed | A list (the consolidated summary covers several); the live repository reads the first for one portfolio. | P09-T02 |
| `name` | - | dto-only | Taken from the PortfolioRef already loaded (a lookup, not a calculation); the consolidated name is the localised "All portfolios". | P09-T02 |
| `base_currency` | `currency` | renamed | Mapped by the live repository. | P09-T02 |
| `value` | `total_value` | renamed | Mapped by the live repository. | P09-T02 |
| `invested` | `net_contributions` | renamed | "Invested" means money put in (deposits minus withdrawals). | P09-T02 |
| `profit_loss` | - | dto-only | From GET /api/v1/portfolios/{portfolio_id}/performance (profit_loss); the live repository combines it with the summary. The app never derives it. | P09-T02 |
| `return_percent` | - | dto-only | From GET /api/v1/portfolios/{portfolio_id}/performance (return_percent); the live repository combines it with the summary. The app never derives it. | P09-T02 |
| `as_of` | `freshness.data_as_of` | renamed | The oldest input the figures use, so the app never shows them as fresher than they are. | P09-T02 |
| - | `holdings_value` | api-only | Read with cash for the Home breakdown. | P09-T02 |
| - | `cash` | api-only | Read for the Home breakdown. | P09-T02 |
| - | `unrealized_pl` | api-only | Read by the Portfolio screen. | P09-T02 |
| - | `realized_pl` | api-only | Read by the Portfolio screen. | P09-T02 |
| - | `currencies` | api-only | Currency breakdown on Portfolio. | P09-T02 |
| - | `unpriced_assets` | api-only | Shown as a notice so totals are never presented as complete when they are not. | P09-T02 |
| - | `freshness.complete` | api-only | Drives the incomplete-data notice. | P09-T02 |

### HoldingSummary - `GET /api/v1/portfolios/{portfolio_id}/holdings` (HoldingOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `symbol` | `asset.symbol` | renamed | Nested, and nullable for user-defined assets: the DTO field becomes optional. | P09-T04 |
| `name` | `asset.name` | renamed | Nested. | P09-T04 |
| `asset_class` | `asset.asset_class` | renamed | Nested. | P09-T04 |
| `value` | `value` | same | Added to the API in P05-T10 (latest valuation; prices from P08-T06). Nullable when unpriced: the DTO becomes optional and the UI shows "no value yet". | P09-T04 |
| `native_value` | `native_value` | same | Added in P05-T10; nullable like value. | P09-T04 |
| `change_percent` | - | dto-only | Daily change needs market prices (ingestion P08-T05; shown by P09-T07). | P08-T05 |
| `as_of` | `value_as_of` | renamed | Mapped by the live repository. | P09-T04 |
| - | `quantity` | api-only | Read by the holdings and investment details screens. | P07-T02 |
| - | `average_cost` | api-only | Read by investment details. | P07-T04 |
| - | `cost_basis` | api-only | Read by investment details. | P07-T04 |

### Account - `GET /api/v1/me` (MeResponse)

Dart: `mobile/wealthsphere_app/lib/features/account/data/account_repository.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `id` | `id` | same |  |  |
| `email` | `email` | same |  |  |
| `base_currency` | `base_currency` | same |  |  |

### CompoundForecastRequest - `POST /api/v1/forecasts/scenarios` (ScenarioForecastIn)

Dart: `mobile/wealthsphere_app/lib/features/forecast/domain/forecast_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `initial_investment` | `initial_investment` | same |  |  |
| `monthly_contribution` | `contribution` | renamed | The amount is per contribution period (monthly, quarterly or yearly), so the API names it contribution; the live repository maps it, also in the echoed assumptions. | P09-T03 |
| `annual_return_percent` | `annual_return_percent` | same |  |  |
| `years` | `years` | same |  |  |
| `contribution_growth_percent` | `contribution_growth_percent` | same |  |  |
| `inflation_percent` | `inflation_percent` | same |  |  |
| `annual_fee_percent` | `annual_fee_percent` | same |  |  |
| `compounding_frequency` | `compounding_frequency` | same |  |  |
| `contribution_frequency` | `contribution_frequency` | same |  |  |
| `conservative_return_percent` | `conservative_return_percent` | same |  |  |
| `growth_return_percent` | `growth_return_percent` | same |  |  |

Limits are shared with the calculator (tests/forecasting/test_limits_shared.py). POST /api/v1/forecasts/compound takes the same fields without the two scenario rates.

### ScenarioResult - `POST /api/v1/forecasts/scenarios` (ForecastProjection)

Dart: `mobile/wealthsphere_app/lib/features/forecast/domain/forecast_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `annual_return_percent` | `annual_return_percent` | same |  |  |
| `nominal` | `nominal` | same |  |  |
| `real` | `real` | same |  |  |
| `final_nominal` | `final_nominal` | same |  |  |
| `final_real` | `final_real` | same |  |  |
| `total_contributions` | `total_contributions` | same |  |  |
| `total_growth` | `total_growth` | same |  |  |
| - | `contributions` | api-only | Not read yet: the forecast screen shows total_contributions. The yearly series is for a contributions-versus-growth chart, which the screen does not have. | P09-T03 |

Series items are {year, value} on both sides (YearValue).

### CompoundForecastResponse - `POST /api/v1/forecasts/scenarios` (ScenarioForecastOut)

Dart: `mobile/wealthsphere_app/lib/features/forecast/domain/forecast_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `currency` | `currency` | same |  |  |
| `scenarios` | `scenarios` | same |  |  |
| `assumptions` | `assumptions` | same |  |  |
| `as_of` | `as_of` | same |  |  |
| `notice` | `notice` | same |  |  |

scenarios is keyed conservative, base and growth on both sides.

### GoalsSummary - `GET /api/v1/goals/summary` (GoalsSummaryOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `on_track` | `on_track` | same |  |  |
| `total` | `total` | same |  |  |
| `items` | `items` | same |  |  |
| `as_of` | `as_of` | same |  |  |
| - | `notice` | api-only | Shown with goal statuses: they are estimates under stated assumptions. | P09-T05 |

### GoalProgress - `GET /api/v1/goals/summary` (GoalSummaryItem)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `id` | `id` | same |  |  |
| `name` | `name` | same |  |  |
| `progress_percent` | `progress_percent` | same |  |  |
| `status` | `status` | same |  |  |
| - | `reached` | api-only | Shows a reached goal as done rather than on track. | P09-T05 |
| - | `target` | api-only | The goal card shows the target. | P09-T05 |
| - | `target_date` | api-only | The goal card shows the date. | P09-T05 |

Full detail (gap, scenarios, required contribution, estimated completion) is GET /api/v1/goals/{goal_id}/progress, for the goal screen (P07-T05, P09-T05).

### NetWorthSummary - `GET /api/v1/net-worth` (NetWorthOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `assets` | `assets` | same |  |  |
| `liabilities` | `liabilities` | same |  |  |
| `net_worth` | `net_worth` | same |  |  |
| `as_of` | `as_of` | same |  |  |
| - | `currency` | api-only | The net-worth currency (also on every Money). | P09-T05 |
| - | `assets_by_class` | api-only | Asset breakdown on the Net Worth screen. | P09-T05 |
| - | `liabilities_by_type` | api-only | Liability breakdown on the Net Worth screen. | P09-T05 |
| - | `liability_lines` | api-only | Each liability with its converted value. | P09-T05 |
| - | `fx_rates` | api-only | FX provenance shown with converted figures. | P09-T05 |
| - | `freshness.complete` | api-only | Drives the incomplete-data notice. | P09-T05 |

### IncomeSummary - `GET /api/v1/income/summary` (IncomeSummaryOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `monthly` | `monthly` | same |  |  |
| `yearly` | `yearly` | same |  |  |
| `as_of` | `as_of` | same |  |  |
| - | `currency` | api-only | Also on every Money. | P09-T05 |
| - | `yearly_gross` | api-only | Income screen: before fees and taxes. | P09-T05 |
| - | `portfolios` | api-only | Income screen: per portfolio. | P09-T05 |
| - | `complete` | api-only | Drives the incomplete-data notice. | P09-T05 |

### AllocationShare - `GET /api/v1/portfolios/{portfolio_id}/allocation` (SliceOut)

Dart: `mobile/wealthsphere_app/lib/shared/domain/wealth_models.dart`

| DTO field | API field | Status | Resolution | Owner |
|---|---|---|---|---|
| `label` | `key` | renamed | The API gives the code (asset class, currency, ISO country, sector) or null for unclassified; the app localises it for display. | P09-T02 |
| `value` | `value` | same |  |  |
| `weight_percent` | `weight_percent` | same |  |  |
| - | `parts` | api-only | Number of positions in the slice (shown in details). | P09-T02 |

The response groups slices by dimension: asset_class, currency_exposure, country and sector.

## DTOs whose API is not built yet

These DEMO DTOs are the proposed contract; the owning task adopts them or updates this mapping.

| DTO | Dart | JSON keys | Owner | Resolution |
|---|---|---|---|---|
| PerformanceSeries, PerformancePoint | `wealth_models.dart` | - | P09-T02 | GET /api/v1/portfolios/{portfolio_id}/risk returns the value series (points with on, value, complete); the live repository maps it to these DTOs. |
| PerformanceMetrics | `wealth_models.dart` | `total_return_percent`, `cagr_percent`, `dividend_yield_percent`, `volatility_percent` | P09-T02 | Composed by the live repository: return from /performance, CAGR as the annualised time-weighted return and volatility from /risk, dividend yield from /income. |
| InsightSummary, EvidenceSourceDto | `wealth_models.dart` | `text`, `as_of`, `sources`, `label`, `provider` | P10-T06 | AI orchestrator (P10-T06): insights carry evidence with provider and as-of time. |
| Chat events | `chat_models.dart` | `type`, `text`, `kind`, `label`, `provider`, `as_of` | P10-T06 | AI orchestrator streaming events (docs/api-conventions.md, Streaming). |
