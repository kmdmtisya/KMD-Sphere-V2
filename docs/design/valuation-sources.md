# Valuation sources: market prices with manual fallback

Status: Implemented in P08-T06. Code: `backend/app/modules/market_data/valuation.py`; used by the portfolio summary and the holdings list. Prices come from ingestion ([market-data-ingestion.md](market-data-ingestion.md)); the summary formulas are in [portfolio-summary.md](portfolio-summary.md).

## 1. The rule

For one open position (units held > 0):

| Asset | Result |
|---|---|
| Valued from prices (a market class with a provider kind) and a price exists | **quantity x latest price**, in the asset's own currency, as of the price's time |
| ... and the user also entered a manual valuation **newer than that price** | the manual valuation: the user's more recent statement of value beats an older quote |
| ... and the manual valuation is older, or the same age | the market price (a tie goes to the price) |
| Valued from prices but no price exists | the latest manual valuation (the fallback) |
| Valued manually (a house, a SACCO share, ...) | its manual valuation only; a stray price is ignored |
| Nothing known | **unpriced**: reported in `unpriced_assets`, left out of the value, never guessed |

A manual valuation is the value of the **whole position**; a price is per unit. The value is then converted into the portfolio currency at the latest FX rate, exactly as before.

## 2. Freshness

- Every value carries its **as-of time**: the price's time or the valuation's.
- A market price older than its kind's window (`freshness.FRESH_FOR`: 4 days for listed assets, which covers a weekend and a holiday; 6 hours for crypto; provisional until DEC-26) is **stale**. A stale price is **still used** (it is the best price known) and flagged, never hidden and never replaced by a guess.
- A manual valuation is never flagged stale: it is the user's own figure, and its as-of time shows its age.

## 3. What the API shows

| Where | Field | Meaning |
|---|---|---|
| Holdings (`GET /portfolios/{id}/holdings`) | `value_as_of` | when the value applied |
| | `value_source` | `price` or `valuation` |
| | `value_stale` | the price is older than its window; null when there is no value |
| | `value_provider` | the provider of the price; null for a manual valuation |
| Summary (`freshness`) | `data_as_of` | the oldest price, valuation or FX rate used |
| | `stale_prices` | positions valued from a stale price (still in the value) |
| | `complete` | unchanged: false only when something is unpriced or unconverted, so a stale price does not make the summary "incomplete" |

## 4. Scope

Only the latest value changes. Historical figures (performance history, valuation as-of a past date) still use manual valuations; market price history for them is a later extension (the closes from the P08-T05 backfill are stored for it).

## 5. Tests

`tests/test_valuation_sources.py`: the rule in isolation (exact arithmetic, newer-wins, tie, manual class, unpriced, staleness by kind) and through the API (price valuing holdings and summary, stale price flagged per holding and in the summary, manual fallback, newer manual override, unpriced, manual class ignoring a price, latest of several prices, OpenAPI fields).
