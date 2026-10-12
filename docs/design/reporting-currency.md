# Reporting currency across the app (P11-T06)

Decisions: [ADR-0010](../adr/0010-global-reporting-currency.md) (one global setting, presentation only), [fx-conversion.md](fx-conversion.md) (snapshots), DEC-29 (no FX scenario overlay in v1).

## The setting

`GET/PATCH /api/v1/me/currency-preferences`: the reporting currency and up to five recent ones, stored on the server (`user_currency_preferences`) so every device shows the same currency. Until the user chooses, it is the profile's base currency when that is a supported currency, else the pivot (`is_default: true`). Only active currencies are accepted (422 otherwise). It is the user's own row; there is no id in the path to probe.

## One snapshot per response

Reporting endpoints open the current snapshot for the request. While it is open, every *latest* rate any service asks the FX service for comes from that snapshot (a request-scoped hook in `market_data/fx_context.py`). Historical rates and ledger postings never do. Each response states the reporting currency, the snapshot id and every rate it used (`reporting.rates`: base, quote, rate, path, published time, provider, status). A pair the snapshot cannot supply (a currency outside the `currencies` table) falls back to the stored rates and is listed with `from_snapshot: false`; it is never guessed.

Because snapshots are content-addressed, the dashboard, the consolidated summary and the net worth requested with the same stored rates carry the same snapshot id, and their totals agree. A total is the sum of its converted parts (each part rounded once to the target's places).

| Endpoint | Reporting currency | Snapshot block |
|---|---|---|
| `GET /api/v1/dashboard` | `?currency=`, default: the setting | `reporting` |
| `GET /api/v1/portfolios/consolidated/summary` | `?currency=`, default: the setting | `reporting` |
| `GET /api/v1/portfolios/{id}/summary` | `?currency=` views the portfolio in another currency; default: its base currency (nothing saved) | `reporting` |
| `GET /api/v1/net-worth` | `?currency=`, default: the setting | `reporting` (plus the existing `fx_rates`) |
| `GET /api/v1/income/summary` | `?currency=`, default: the setting | `reporting` |
| `GET /api/v1/goals/summary`, `/goals/{id}/progress` | goals stay in their target currency; `target_in_reporting` (and `current_value_in_reporting`) beside it | `reporting` |
| `POST /api/v1/forecasts/*` | `?reporting_currency=` adds `in_reporting`: the end values at today's rate, with the note that future exchange rates are not forecast; inputs and projection unchanged | `in_reporting.snapshot_id` |

## What stays in the portfolio's own currency

Holdings, performance (returns, profit, money-weighted and time-weighted returns), allocation and risk stay in the portfolio's base currency. They are computed from ledger postings at their own dates and rates; translating them at today's rate would mix a current rate into historical results (QG-22.4) and misstate gains. The per-portfolio summary's `?currency=` gives a current-rate view of the portfolio's value when one is wanted.

## Never changed by a switch

Balances, transaction amounts and their rates, portfolio base currencies, goal targets and forecast inputs. A test switches the setting several times and compares the stored rows before and after.

## Not built

The optional FX scenario overlay on forecasts (P11-T06.4) is not built in v1 (DEC-29).
