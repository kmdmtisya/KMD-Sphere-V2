# Portfolio Summary (P05-T08)

Status: Implemented in P05-T08. Market prices arrive in P09; until then assets are valued from manual valuations (P05-T07) or reported as unpriced. Performance figures (TWR, XIRR, returns over periods) are analytics (P06).

The backend is the only place these figures are computed. Every figure is computed at full precision and rounded half-up to the currency's minor units only when published (ADR-0006).

## 1. Inputs (one portfolio, base currency B)

- **Holdings** (ADR-0012): per asset, quantity, cost basis, realised profit, income and expenses, already in B at each posting's own rate.
- **Latest valuations** (P05-T07): per asset, value, currency and as-of time.
- **Ledger entries** (reversed entries and their reversals left out), for cash and contributions, each with its currency and its rate to B.
- **Latest FX rates** to B for every currency that appears (P05-T06 "latest" rule).

## 2. Valuing positions

| Position | Value |
|---|---|
| Has a latest valuation, and is not closed | The valuation (the whole position), converted to B at the latest rate |
| Closed (a holding with quantity 0) | Not valued |
| No valuation (and no price yet, P09) | **Unpriced**: listed, left out of `holdings_value` |

An asset with valuations but no ledger entries (a house bought before using the app) is valued; its cost basis is unknown.

## 3. Cash

Cash per currency is the sum of every entry's cash effect in its own currency:

| Type | Cash effect |
|---|---|
| DEPOSIT | + gross - fees - taxes |
| WITHDRAWAL | - gross - fees - taxes |
| BUY | - (gross + fees + taxes) |
| SELL | + gross - fees - taxes |
| DIVIDEND, INTEREST, COUPON, RENT, DISTRIBUTION | + gross - fees - taxes |
| FEE, TAX | - (gross + fees + taxes) |
| TRANSFER_IN, TRANSFER_OUT | - fees - taxes (units move, cash does not) |
| VALUATION_ADJUSTMENT | none |

Each currency's balance is converted to B at the latest rate. A balance can be negative when deposits are not recorded; it is shown as it is, never hidden.

## 4. Figures (all in B)

- `holdings_value` = sum of valued positions.
- `cash` = sum of converted cash balances.
- `total_value` = `holdings_value` + `cash`.
- `cost_basis` = cost basis of the valued positions that came from the ledger (historical rates).
- `unrealized_pl` = value - cost basis, over valued positions with a ledger cost basis.
- `realized_pl`, `income`, `expenses` = sums over all holdings, plus asset-less INTEREST (income) and asset-less FEE and TAX (expenses), each at its posting's own rate.
- `net_contributions` = deposits - withdrawals (gross, at each posting's own rate).

## 5. Currency breakdown

Per native currency: the valued positions and cash in that currency, in the currency itself and converted to B, and the share of `total_value`. Shares are given to 2 decimals and allocated by largest remainder so that they add up to exactly 100.00 (ADR-0006). They are left out (null) when the total is not positive or a part is negative, because a percentage share is then meaningless.

## 6. Freshness and completeness

- `computed_at`: when the summary was computed.
- `data_as_of`: the **oldest** input used (valuation as-of or FX rate time), so the summary is never presented as fresher than its stalest part.
- `stale_fx`: currencies whose rate is older than one day (provisional threshold, DEC-26).
- `unpriced_assets`: open positions without a value.
- `unconverted_currencies`: currencies with no usable rate to B. Amounts in them are left out of every total.
- `complete`: true only when nothing is unpriced or unconverted.

## 7. Consolidated summary

`GET /api/v1/portfolios/consolidated/summary?currency=XXX` (default: the user's base currency) adds up the user's active (not archived) portfolios.
- Every figure of each portfolio, including its currency breakdown, is converted from its base currency at the latest rate, so the consolidated totals and breakdown reconcile exactly.
- Native amounts per currency are added as they are.
- Freshness takes the oldest input of all portfolios and of the conversions.

Converting cost basis at today's rate is a simplification of the consolidated view only. Each portfolio keeps historical cost in its own currency.
