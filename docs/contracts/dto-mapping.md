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
| `profit_loss` | - | dto-only | total_gain from the performance service (P06-T03, docs/design/performance.md), published by the analytics API. The app never derives it. | P06-T09 |
| `return_percent` | - | dto-only | simple_return from the performance service (P06-T03; method stated in docs/design/performance.md), published by the analytics API. The app never derives it. | P06-T09 |
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
| - | `contributions` | api-only | Cumulative paid-in series for the contributions-versus-growth chart. | P09-T03 |

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

## DTOs whose API is not built yet

These DEMO DTOs are the proposed contract; the owning task adopts them or updates this mapping.

| DTO | Dart | JSON keys | Owner | Resolution |
|---|---|---|---|---|
| PerformanceSeries, PerformancePoint | `wealth_models.dart` | - | P06-T09 | Historical values come from the series builder (P06-T08); the analytics API (P06-T09) adopts these shapes or updates this mapping. |
| AllocationShare | `wealth_models.dart` | `label`, `value`, `weight_percent` | P06-T04 | Allocation analytics; weights come from the server (largest remainder, ADR-0006). |
| PerformanceMetrics | `wealth_models.dart` | `total_return_percent`, `cagr_percent`, `dividend_yield_percent`, `volatility_percent` | P06-T09 | Returns and CAGR from the performance service (P06-T03), dividend yield from income (P06-T05), volatility from risk (P06-T08); published by the analytics API (P06-T09). |
| NetWorthSummary | `wealth_models.dart` | `assets`, `liabilities`, `net_worth`, `as_of` | P06-T07 | Net worth and liabilities module. |
| IncomeSummary | `wealth_models.dart` | `monthly`, `yearly`, `as_of` | P06-T09 | monthly = TTM net / 12 and yearly = TTM net from the income service (P06-T05, docs/design/income.md), published by the analytics API. |
| GoalsSummary, GoalProgress | `wealth_models.dart` | `id`, `name`, `progress_percent`, `status`, `on_track`, `total`, `items`, `as_of` | P06-T06 | Goals module. |
| InsightSummary, EvidenceSourceDto | `wealth_models.dart` | `text`, `as_of`, `sources`, `label`, `provider` | P10-T06 | AI orchestrator (P10-T06): insights carry evidence with provider and as-of time. |
| Chat events | `chat_models.dart` | `type`, `text`, `kind`, `label`, `provider`, `as_of` | P10-T06 | AI orchestrator streaming events (docs/api-conventions.md, Streaming). |
