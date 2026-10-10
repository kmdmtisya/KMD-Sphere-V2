# Multi-currency reporting and FX management (FXCUR): design

Status: **Proposed**, awaiting user approval (P11-T01). Nothing here is implemented yet. Related: [ADR-0010](../adr/0010-global-reporting-currency.md), `EXECUTION_PLAN.md` phase P11 (FXCUR-01…12 = P11-T01…T12), quality gates QG-21…QG-25 (QG-FXCUR-01…05).

## 1. Purpose and rules

Users choose one **reporting currency** (AED, USD, KES, EUR, GBP, JPY, CHF, CAD, AUD, ZAR initially; any ISO 4217 code later) and every financial figure in WealthSphere is shown in it.

Non-negotiable rules:

1. **Presentation only.** Changing the reporting currency never changes balances, transaction amounts, transaction FX rates, portfolio base currencies, goal target currencies, forecast assumptions or any historical record. Conversions are read-only views.
2. **One global setting** (the user's recommendation, adopted). It is a user preference stored on the server and synced across devices, set from Settings and from the Total Wealth figure on Home; it is not a calculator feature.
3. **Real rates only.** Every converted figure comes from a provider rate with provider, rate type, timestamp and status. If no usable rate exists, the figure says so; no rate is invented or hard-coded.
4. **Honest freshness.** Rates are labelled current, delayed, indicative, cached or unavailable. Cached data is never labelled live. Tick-level real-time FX is not assumed.
5. **Consistency.** All figures on one screen, report or AI answer use one rate snapshot, so totals always equal the sum of their parts.
6. **Exact arithmetic.** Python `Decimal` and PostgreSQL `NUMERIC` on the backend, `Decimal`/`Money` in the app (ADR-0003); rounding per ADR-0006, once, at the end, to the target currency's minor units.
7. **The backend converts.** The app never multiplies amounts by rates; it asks the API for figures in the reporting currency (or calls `POST /fx/convert`).

## 2. What already exists (reused, not duplicated)

| Existing work | What it gives FXCUR | FXCUR extends it with |
|---|---|---|
| P05-T01 `fx_rates` table | Stored rates | rate_type, status, provider, rate_timestamp, retrieved_at, rate path |
| P05-T06 FX service | Conversion into a portfolio's base currency, historical vs latest rate selection, rounding tests | Reporting-currency conversion, snapshots, cross-rates, per-currency precision |
| P08-T02/T03 provider abstraction and adapters | Pluggable providers with contract tests | FX-specific adapters, primary/fallback selection |
| P08-T05 price and FX ingestion with backfill | Current and historical rates | Refresh cadence within quotas, cache, staleness status |
| P04-T05 `/me` and `PATCH /me/preferences` | User preference storage | `GET/PATCH /me/currency-preferences` (reporting currency, recent currencies) |
| P07-T08 Settings, P09-T02 preference sync | Settings screen and sync | Reporting-currency setting |
| Design system `CurrencyAmount`, `Money` | Exact display with native-currency line | Rate/status chip, selector sheet |
| P10 tool framework | Authorised AI tools | Six currency tools |

## 3. Currency concepts

| Concept | Meaning | Changed by |
|---|---|---|
| Native currency | The currency an asset or transaction is denominated in | Never (it is a fact) |
| Portfolio base currency | The currency a portfolio is accounted in (UAE portfolio = AED, Kenya portfolio = KES) | The user editing the portfolio (an accounting change, not a display change) |
| Reporting currency | The currency the user wants to see everything in | The global setting |
| View-as currency | A temporary currency for one portfolio screen | The user, for that view only; not saved |

## 4. Rates and their status

Each rate: base, quote, rate (`NUMERIC(28,12)`), provider, rate_type (`mid_market`, `indicative`, `delayed`), rate_timestamp (provider time), retrieved_at, status (`current`, `cached`, `stale`, `unavailable`), and for derived rates the path.

- **Direction.** A rate means 1 base = rate quote. Inverses are derived (1/rate, computed in Decimal with enough precision) and recorded as derived.
- **Cross-rates.** If AED→KES is not quoted, use AED→USD→KES through the pivot (DEC-27, proposed USD); both legs must be from the same snapshot and the path is returned.
- **Staleness.** Thresholds per provider tier (DEC-26). Past the threshold a rate is `stale`; the UI shows "Cached · last updated 09:15" or "Unavailable".

## 5. FX provider service

Provider abstraction from P08 with a configurable primary and fallback (DEC-25; candidates Open Exchange Rates, ExchangeRate-API, Currencylayer, OANDA or the P08 provider). Selection criteria: coverage of the 10 initial currencies, accuracy, update frequency, history, licence for in-app display and caching, reliability, rate limits and cost.

Refresh: on a schedule matching the provider's real update frequency, on app start when the cache is older than the TTL, and on user request (`POST /fx/refresh`, authenticated and rate-limited). Failures retry with exponential backoff and jitter, then fall back to the second provider; if both fail the last good rate stays with status `cached`/`stale`. One batch call fetches all needed pairs; the central cache (Redis) serves every request so UI components never trigger provider calls.

## 6. Conversion engine

```text
converted = round_half_up(original_amount × rate, minor_units(target))     # once, at the end
```

- Inputs and outputs are `Decimal`; minor units come from the `currencies` table (JPY 0, most others 2).
- **Snapshots.** A snapshot is an immutable set of rates with an id and timestamp. Each read API resolves one snapshot per request; every figure in the response uses it, and the response returns the snapshot id, rates, providers and timestamps. Reports store the snapshot id.
- **Aggregation.** Holdings are converted per line and the total is the sum of converted lines; the response states the rounding convention so the reconciliation test can assert equality.

## 7. Historical rates

Three separate concepts, never mixed:

| Rate | Used for |
|---|---|
| Transaction rate | The rate recorded with a transaction (P05-T06); never recomputed |
| Historical valuation rate | Converting a past valuation or past income on its date |
| Current reporting rate | Converting today's values into the reporting currency |

Performance history, realised and unrealised gains, net-worth trends and historical income use historical rates for each date. If a date has no rate, the response flags it (`rate_missing: true`, nearest-date fallback only if the user's report settings allow it and it is labelled).

## 8. Where the reporting currency applies

Home, Portfolio overview, holdings, analytics, Net Worth, Passive Income, Goals, Calculator, Forecast, AI Wealth Copilot, AI Investment Intelligence (P12), Forex Intelligence (P13) and reports/exports. Rules:

- **Goals** keep their target currency; the goal card shows the target in its own currency and, secondarily, in the reporting currency.
- **Forecasts** keep their inputs and return assumptions; only the presentation converts, using today's rate, labelled as such. Future FX movements are never presented as predictable. An optional FX scenario overlay (DEC-29) would be labelled illustrative.
- **Portfolios** keep their base currency; "view as" shows a portfolio in another currency without saving anything.

## 9. API (versioned, OpenAPI-first)

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/currencies` | Supported currencies with name, symbol, minor units |
| `GET /api/v1/fx/rates` | Current rates for a base and quote list, with status and snapshot id |
| `GET /api/v1/fx/rates/{base}/{quote}` | One rate, direct or derived, with path |
| `GET /api/v1/fx/history` | Historical rates for a pair and date range |
| `POST /api/v1/fx/convert` | Convert an amount (optionally on a date) with the rate used |
| `POST /api/v1/fx/refresh` | Request a refresh (authenticated, rate-limited, quota-aware) |
| `GET/PATCH /api/v1/me/currency-preferences` | Reporting currency and recent currencies |

Existing read endpoints gain `?currency=` (default: the preference) and return `reporting_currency`, `fx_snapshot` and per-figure provenance. Errors are RFC 7807 (`fx_rate_unavailable`, `unsupported_currency`).

## 10. Data model (migrations in P11-T02)

- `currencies`: id, code (ISO 4217, unique), name, symbol, decimal_places, is_active.
- `fx_rates` (extended): base_currency, quote_currency, rate NUMERIC, provider, rate_type, rate_timestamp, retrieved_at, status; index (base, quote, rate_timestamp DESC).
- `fx_snapshots`: id, created_at, rate ids (or a JSON of rates) — immutable.
- `user_currency_preferences`: user_id, reporting_currency, recent_currencies, updated_at.
- `fx_conversion_audit`: id, user_id, source_currency, target_currency, source_amount, converted_amount, rate_used, rate_timestamp, provider, snapshot_id, conversion_type, created_at. Scope and retention per DEC-28: material conversions (AI answers, reports, explicit converter use) are audited; cosmetic display switches are not.

## 11. Mobile UX

- **Home:** a currency chip next to Total Wealth ("USD ▾") and an FX status line ("FX updated 10:30", or "Cached · 09:15", or "Rates unavailable").
- **Settings:** Reporting currency row.
- **Selector sheet:** search, code, name, symbol, selected indicator, recent currencies, last rate update.
- **Switching:** figures update in place (no full-screen reload, scroll and navigation kept); a figure whose rate is not ready shows a skeleton, and a figure that cannot be converted says so.
- **Converter screen** (More → Currency converter): source, target, amount, converted amount, rate, timestamp, swap, refresh, recent conversions; uses `POST /fx/convert`.
- Light/dark, 2.0x text, RTL and the accessibility sweep apply as for every screen.

## 12. AI Copilot tools (P10 framework)

`get_current_fx_rate(base, quote)`, `get_historical_fx_rate(base, quote, date)`, `convert_currency(amount, from, to, rate_date)`, `get_portfolio_value(portfolio_id, currency)`, `get_net_worth(currency)`, `get_fx_exposure(portfolio_id)`. All validate inputs and enforce ownership; every number returned carries rate, provider, timestamp and snapshot; the output guard rejects any rate not present in a tool result. Tool conversions use the same service as the API, so they match.

## 13. Performance, security and observability

Central cache with TTL, batch retrieval, one snapshot per request, per-holding conversion done in the database or service in one pass; no provider calls from UI paths. Refresh endpoint rate-limited per user and globally; provider keys in the secret store. Metrics: provider latency and errors, fallback activations, cache hit rate, stale-rate ratio, quota use; alert on sustained fallback or staleness.

## 14. Tests

| Area | Tests |
|---|---|
| Accuracy | Provider-response parity, direction and inverse cases, cross-rate paths, Decimal precision, minor-unit rounding (QG-21) |
| Consistency | Totals equal the sum of converted parts per snapshot; originals unchanged; mixed-currency aggregation; historical rates per date; dashboard vs report agreement (QG-22) |
| Reliability | Outage, fallback, staleness, cache TTL, quota (QG-23) |
| Mobile | Selector, app-wide update, persistence and sync, dark/light, loading/error, accessibility (QG-24) |
| AI | Authorised tools only, no invented rates, parity with the API, ownership (QG-25) |

## 15. Open decisions

DEC-25 provider(s) and licence · DEC-26 refresh cadence and staleness thresholds · DEC-27 pivot currency and precision · DEC-28 audit scope and retention · DEC-29 FX scenario overlay in v1 or later.
