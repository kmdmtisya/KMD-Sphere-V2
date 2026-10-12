# Live repositories and the data-source switch (P09-T01)

The app reads either bundled DEMO fixtures or the WealthSphere API. Screens never know which.

- **Mode:** `DataSourceMode { demo, live }`, started from `--dart-define=WS_DATA_SOURCE=demo|live` (default `demo`; anything else fails at start). Every repository provider chooses its implementation from `dataSourceModeProvider`, so switching mode needs no screen change. A live repository that is not wired yet throws `UnsupportedError` (`liveNotWired`) instead of showing demo data as if it were real. T09 adds the release policy.
- **Client:** `buildApiClient` (Dio): bearer token with refresh and one retry, `X-Correlation-ID`, short timeouts, no logging interceptor.
- **Base class:** `LiveRepository` (`lib/core/network/live_repository.dart`): `getObject`, `getList`, `send` (with `Idempotency-Key` for writes) and `sendEmpty`. All parsing goes through the strict `JsonReader` (ADR-0013); a body of the wrong shape becomes `ApiErrorKind.invalidResponse` naming the field path, never a value. Live repositories return what the server says and never recalculate money.
- **Errors:** every failure is an `ApiException` (network, unauthenticated, forbidden, notFound, validation, rateLimited, server, invalidResponse, unexpected). `loadFailureOf` groups them into `LoadFailure` (offline, signedOut, forbidden, notFound, busy, unknown) and `LoadErrorView` words each one: offline, session ended (no Retry), refused (no Retry), missing, busy, generic. It shows the API support reference when there is one, never exception text. `AsyncValueView` uses it by default, so existing screens get the right state with no change.
- **DTOs:** hand-written on `JsonReader`, checked against the API by `docs/contracts/dto-mapping.json` (ADR-0013). The unused Freezed, json_serializable and build_runner dependencies were removed here, as that ADR planned.

## Home and Portfolio (P09-T02)

`LiveDashboardRepository` and `LivePortfolioRepository` read the API; `SyncedDashboardLayoutRepository` keeps the Home layout on the device and in the account (`PATCH /me/preferences`; the account wins on load, the device copy is used offline).

| Screen data | Endpoint |
|---|---|
| Greeting | `GET /me` (display name, else the email's local part) |
| Net worth, income, goals | `GET /net-worth`, `/income/summary`, `/goals/summary` |
| Portfolio list, name | `GET /portfolios`, `/portfolios/{id}` |
| Summary | `/portfolios/{id}/summary` + `/performance` (profit and return); `/portfolios/consolidated/summary` for all portfolios |
| Chart | `/portfolios/{id}/risk` points (incomplete points left out) |
| Allocation | `/portfolios/{id}/allocation`, asset-class slices named from `/asset-classes` |
| Metrics | return from `/performance`; annualised return and volatility from `/risk`; yield from `/income` |
| Holdings | `/portfolios/{id}/holdings` |

Rules kept: no figure is added, converted or derived in the app. A missing figure is null and shown as "Not available" or "No value yet"; an unpriced position sorts last and is never shown as zero; `DataQualityNotice` says when a total is incomplete or uses stale prices; Home shows no AI insight until the AI service exists (P10-T06).

**Known gap (follow-up):** the API has a consolidated *summary* only. For "All portfolios" there is no profit and loss, return, chart series, allocation or metrics, so those are empty or "Not available" rather than summed on the device. All-portfolio holdings are the per-portfolio lists joined (a position held in two portfolios appears twice). A backend consolidated performance, allocation and risk endpoint would close it. The "Unclassified" allocation label and the greeting fallback "there" are English literals in the repository layer.

## Calculator and forecast (P09-T03, resolves DEC-03 in live mode)

`LiveForecastRepository` posts the calculator inputs to `POST /api/v1/forecasts/scenarios` and shows the engine's three scenarios. The DTO's `monthly_contribution` is sent and read back as the API's `contribution`, so the echoed assumptions equal the request and the demo-mismatch banner never appears. In live mode the calculator and forecast screens show no DEMO badge. A refused input (422) says the values are outside the limits; offline, session-ended and busy failures use the shared wording. The calculator opens with `ForecastInputLimits.defaults`, the same limits the backend enforces.

## Holdings, ledger and investment detail (P09-T04)

- **Ledger:** `LiveTransactionRepository` reads `/portfolios/{id}/transactions` page by page (cursor, 100 per page), names each asset from `GET /assets/{id}` (`AssetCatalog`, cached per session), and posts new entries with an `Idempotency-Key` made once per reviewed entry, so retrying a failed save can never record it twice. A trade sends quantity and unit price only; the server derives the gross amount and the app shows the server's figure. Corrections stay append-only: a linked reversal (`/reversal`); an entry already reversed, or a reversal, is refused before calling, and a 409 from the server is reported as "already reversed".
- **After a save or a correction** the ledger, holdings, summaries, chart, allocation, metrics and Home figures are re-read from the server (`refreshLedger`); nothing is adjusted on the device.
- **Holdings** (from P09-T02) carry the asset id; screens open an investment by `detailKey` (asset id live, symbol in DEMO).
- **Investment detail:** `LiveInvestmentRepository` shows the asset and one position per portfolio that holds it (quantity, average cost, cost basis, value as reported). Not supplied by the API, so empty rather than invented: market price, change, price history (P09-T07), fundamentals, research, per-asset income, unrealised gain or loss per position (the app does not compute value minus cost).

## Goals, net worth and income (P09-T05)

- **Goals:** `LiveGoalRepository` reads `/goals` and each goal's `/goals/{id}/progress`. Status, progress, gap, scenarios, estimated completion and the server's assumption notice are shown as returned; the Goals list and the Home goals card show the API's notice ("estimates ... not guaranteed"). A goal the server cannot measure (422) is shown without figures. Create and update send amounts and rates as strings; a 409 is reported as "name taken" or "too many goals" from the server's message.
- **Net worth:** `/net-worth` totals, asset-class names and shares as given; each liability at its converted value, or at its own-currency balance when it could not be converted (the total then carries the incomplete notice).
- **Income:** `/income/summary` monthly and yearly totals and per-portfolio yearly income (no share is shown: the server gives none and the app does not compute one). Recent payments are the latest income entries in the ledger (dividends, interest, coupons, rent, distributions), excluding reversed entries.

## Prices, watchlist and alerts (P09-T07)

- **New endpoint** `GET /api/v1/assets/{asset_id}/prices?start&end` (market_data module): the latest stored price (unrounded unit price, provider, as-of, `stale`) and one stored close per day for the period; `data_type: delayed`; nothing interpolated. Only assets the user may see (404 otherwise; IDOR test registered). The P08-T09 licence guard lists it as reviewed: per user, authenticated, stored data the user already sees.
- **Watchlist latest price** is now unrounded too (`price` as a decimal string plus `currency`): rounding a unit price to the currency's minor units showed tiny crypto prices as 0.00.
- **Investment screen:** price, provider and time from that endpoint, an "out of date" label when stale, "No market price yet" when none; the chart shows the stored closes only. No daily change is shown (the API has none).
- **Watchlist and alerts screen** (More > Watchlist and alerts): followed investments with their latest stored price, its age and an out-of-date label; alerts with their condition and status (pause, resume, re-arm, delete); recently triggered alerts (mark seen). A price alert is set from an investment's page, in the asset's currency. DEMO mode keeps the lists in memory and never fires an alert.

## Data-source governance (P09-T09)

- **Release builds refuse DEMO data.** `WS_DATA_SOURCE` defaults to `live` in a release build (`dart.vm.product`) and `demo` otherwise. `AppConfig.fromEnvironment` throws at start if a release build asks for anything but `live`, and `DataSourceModeNotifier` refuses `demo` (at start and in `set`) when `releaseBuildProvider` is true (tests override it). Tests: `test/guards/data_source_governance_test.dart`.
- **DEMO labelling follows the data.** Screens whose data comes from the repositories use `DataSourceBadge`, which shows DEMO only while the mode is demo. The AI screens (AI Wealth, Portfolio Doctor, Opportunities and its comparison) are demo in every mode until the AI services exist (P10): their repositories are the demo ones, and they show the unconditional `DemoBadge`. A guard test fails if any other screen shows `DemoBadge`/`DemoBanner` directly, if `liveNotWired` is used again, or if demo fixtures are read outside `demo_support.dart`.
- **The Home insight** shows nothing in live mode (no AI yet) rather than a demo sentence.
