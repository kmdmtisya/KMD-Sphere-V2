# FXCUR reconciliation with existing work (P11-T01)

Status: **for your review**. ADR-0010 is already Accepted and the design in [multi-currency-design.md](multi-currency-design.md) was approved on 2026-10-10. This note is the inventory the task asks for, the extension map, and the decisions DEC-25 to DEC-29 with a recommendation each. Facts below were read from the code on 2026-10-12.

## 1. Inventory of what exists

| Area | Where | What it does today |
|---|---|---|
| Rate storage | `market_data/models.py` `FxRate`, table `fx_rates` | 1 base = `rate` quote, unique per pair, provider and `rate_timestamp`; `retrieved_at`; rate > 0; ISO-shaped codes. No `rate_type` or `status` column |
| Rate choice and arithmetic | `market_data/fx.py` | `select` picks the rate valid at a time from either direction (inverts when needed), marks it `stale`, ties broken by provider name; `convert_exact` / `convert` round half-up to the target's minor units once. Raises `FxRateUnavailable` (mapped to 404 `fx-rate-unavailable`) |
| API | `market_data/api.py` | `GET /api/v1/fx-rates` returns the rate WealthSphere would use, with provenance |
| Provider layer | `market_data/providers/*` | `MarketDataProvider` protocol with `get_fx_rate` and `get_fx_history`; adapters: ECB, CoinGecko, Twelve Data, fake; resilience (retry, fallback chain), throttle |
| ECB adapter | `providers/ecb.py` | Daily, EUR base, any pair crossed through EUR, labelled indicative. **Does not publish AED or KES** (such a pair is `UnsupportedKind`, so the chain moves on) |
| Ingestion | `market_data/ingestion.py`, worker `ingest_fx` (daily 16:30 UTC) and backfill jobs | Stores current and historical rates idempotently |
| Consumers of conversion | `portfolio/summary_service`, `risk_service`, `transactions/holdings_service`, `networth`, `goals`, AI tools | Convert into a portfolio's base currency or the requested `currency`, per line, with unconverted currencies reported as incomplete |
| User currency | `identity/models.py`: `base_currency` on the profile, `preferences` JSONB (UI only) | One profile base currency; no reporting-currency preference |
| Mobile | `CurrencyAmount`, `Money`, Settings screen, preference sync | Exact display; no reporting-currency setting or rate/status chip |

## 2. Extension map (nothing duplicated)

| FXCUR capability | Extends | New? |
|---|---|---|
| Rate status, rate type | `fx_rates` (add columns, backfill existing rows as `mid_market`/`indicative`) | columns only |
| Reporting conversion, cross-rates, snapshots | `fx.py` `select`/`convert` (add pivot path and an immutable snapshot around the same functions) | `fx_snapshots` table |
| Primary and fallback provider, refresh cadence, quota | provider registry and resilience chain, `ingest_fx` job | one new adapter if DEC-25 needs it |
| `GET /fx/rates`, `/fx/convert`, `/fx/history` | `GET /api/v1/fx-rates` (same service and provenance) | new routes, same service |
| Reporting-currency setting | profile and preferences service; `GET/PATCH /me/currency-preferences` | table `user_currency_preferences` |
| `?currency=` on read APIs | the existing `currency` parameter on summary, net worth and analytics | wiring the default from the preference |
| Currency tools | P10 tool registry (same pattern as `get_net_worth`) | six tools |
| Mobile chip, selector, converter | design-system `CurrencyAmount`, Settings, live repositories | selector sheet, converter screen |
| Conversion audit | audit module | table `fx_conversion_audit` |

Two findings that change plans:
1. **`fx_rates` already holds most of the rate record** (provider, timestamp, retrieved_at); P11-T02 only adds type and status and the snapshot and preference tables.
2. **The ECB cannot supply AED or KES**, two of the ten launch currencies. A second provider is required for those pairs, not only as a failover. This is what DEC-25 decides.

## 3. Decisions

| # | Decision | Recommendation | Needs |
|---|---|---|---|
| DEC-25 | **Decided 2026-10-12: Option A, ExchangeRate-API** as the commercial provider (Pro plan, about USD 10 a month, hourly; monthly budget to be confirmed). ECB stays primary where it publishes. Production use waits for written confirmation of its terms for in-app display and caching, and for AED and KES coverage. Original analysis: FX provider(s) | Keep ECB as the primary for the currencies it publishes (free, daily, indicative). Add one commercial FX API as the fallback **and** the source for AED, KES and other pairs the ECB lacks. Choose among Open Exchange Rates, ExchangeRate-API, Currencylayer and OANDA on three facts I have not verified and will not assume: coverage of the ten currencies, a licence that allows in-app display and caching, and price. I recommend you pick the vendor and budget; I will then build the adapter against its documented API and recorded fixtures only (no key, no live call) | **You** |
| DEC-26 | Refresh and staleness | ECB: refresh daily (existing 16:30 UTC job), `current` for 36 hours, `cached` up to 72 hours, `stale` beyond. Commercial provider: hourly where the plan allows, `current` for 2 hours, `cached` up to 24 hours, `stale` beyond. Statuses are always shown; cached is never labelled live | Approve |
| DEC-27 | Pivot and precision | Pivot USD for cross-rates when no direct pair exists (both legs from one snapshot, path returned). Display precision is the currency's minor units from the `currencies` table (JPY 0, most 2); rates are stored at 12 decimals and rounded once at the end (ADR-0006) | Approve |
| DEC-28 | Conversion-audit scope | Audit conversions that become records: AI answers, generated reports and exports, and explicit converter use. Do not audit cosmetic switches of the display currency. Retention follows the audit policy | **You** |
| DEC-29 | FX scenario overlay on forecasts | Later, not in v1: forecasts convert at today's rate and say so; no future FX movement is shown as predictable | **You** |

## 4. What approval means

Approving P11-T01 confirms the design and extension map above, accepts DEC-26 and DEC-27 as proposed, and records your answers to DEC-25, DEC-28 and DEC-29. It starts no implementation; P11-T02 (data model) is the next task and is a separate step.
