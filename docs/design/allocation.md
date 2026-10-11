# Allocation and concentration

Status: Implemented in P06-T04. The maths is pure and deterministic: `backend/app/modules/analytics/allocation.py` uses Decimal only and has no I/O. `backend/app/modules/portfolio/allocation_service.py` applies it to one portfolio's summary. It is published by the analytics API (P06-T09) and reviewed in P06-T10.

## 1. What is allocated

The portfolio's `total_value` from the summary (docs/design/portfolio-summary.md), split into parts in its base currency:

- **each valued position**, at its latest valuation converted at the latest rate;
- **each currency's cash balance**, converted at the latest rate.

Unpriced positions and amounts in currencies without a rate are not part of `total_value`, so they are not allocated. The result carries the summary's `complete` flag and the list of unpriced assets, so an allocation is never presented as complete when it is not.

## 2. Dimensions

| Dimension | A position's key | Cash's key |
|---|---|---|
| `asset_class` | the asset's class code (stock, etf, bond, real_estate, ...) | `cash` |
| `currency` | the currency of its valuation | the cash currency |
| `country` | the asset's `country` (ISO 3166-1 alpha-2) | unclassified |
| `sector` | the asset's `sector` metadata (stocks and REITs carry one), with surrounding spaces removed | unclassified |

- A part without a value for the dimension goes to the **unclassified** slice (key `null`). Every dimension therefore adds up to the same total.
- Country and sector come only from asset data, never from a guess. Cash has no country: a USD balance can be held anywhere.
- Allocation by currency reconciles with the summary's currency breakdown.

## 3. Slices and weights

- A slice is the sum of the parts with the same key, together with the number of parts in it.
- Slices are ordered by value (largest first), then by key, with unclassified last. The order is deterministic.
- **Weights** are percentages of the dimension's total, to 2 decimals. They are allocated by the largest-remainder method so they add up to exactly 100.00 (ADR-0006, `app/core/money.percentages`); remainder ties go to the earlier slice in the order above.
- Weights are `null` (undefined) when the total is not positive or any part is negative (negative cash). A percentage share is meaningless then.

## 4. Concentration

**Positions:** every valued position and every cash balance counts as one position.

| Measure | Definition |
|---|---|
| `hhi` | Herfindahl-Hirschman index: the sum of each position's squared weight (as fractions). It ranges from 1/n (equal weights) to 1 (a single position). |
| `effective_positions` | 1 / `hhi`: the number of equal positions with the same concentration |
| `top_1`, `top_3`, `top_5` | the share of the total held by the largest 1, 3 and 5 positions (all of it when there are fewer) |
| `largest` | the largest position (asset id, or `cash:<currency>`) |

- The same index is given for each allocation dimension (for example, how concentrated the asset classes are).
- Measures are `null` when the total is not positive or a part is negative, for the same reason as the weights.
- Measures are unrounded. The API publishes them to 4 decimals (index and shares) or 2 (effective positions), half-up.
- No thresholds or judgements are applied here. Interpreting concentration (for example "highly concentrated") is the Portfolio Doctor's job (P12), with stated thresholds.

## 5. Consolidated view

The consolidated summary carries the same per-position values, converted from each portfolio's base currency. Allocation can therefore also run on it; the API decides whether to expose that (P06-T09). A position held in several portfolios counts as one position.
