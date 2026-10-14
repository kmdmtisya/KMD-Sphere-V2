# Forex trade risk calculator, as built (P13-T07)

This document covers the position-size and risk calculator and the contract specifications it uses. The design is in [forex-technical-design.md](forex-technical-design.md) section 9. The formulas are in [financial-methods.md](../financial-methods.md) section 21, and the tests are rows K-01 to K-06 of the financial test matrix.

**Scope.** The calculator is for study and paper trading:
- It sizes a hypothetical position.
- Nothing is stored, and nothing is placed: there is no order path (hard rule 1).
- No language model takes part.
- All arithmetic is in `Decimal`, and every rounding is stated (ADR-0006).

## 1. Code

The code is in `backend/app/modules/forex/risk/`:

| File | Content |
|---|---|
| `contract_specs.json` | The contract specifications: version 1, DEMO defaults, `unreviewed` |
| `specs.py` | The `forex_contract_specs` table (migration 0023), loading and validation, `sync`, `mark_reviewed` and `compare_with_provider` |
| `engine.py` | The calculator: pip value, costs, size, loss and profit, risk/reward, margin, leverage, exposure, warnings and disclosures |
| `conversion.py` | The quote-currency to account-currency rate from stored quotes, with its provenance |
| `api.py` | The two endpoints (section 4) |

## 2. Contract specifications (DEC-24)

**The table.** Each row holds:
- contract size;
- lot step, and minimum and maximum lots;
- margin rate (its inverse is the maximum leverage);
- commission per lot per side, in the quote currency;
- a slippage assumption in pips per fill.

**Versions.**
- A row is never edited. A new file version supersedes the active row, and the old row is kept as `superseded`.
- If the same version is loaded with different values, it is refused: a change needs a new version.
- A partial unique index allows one active version per pair.
- Every calculation names the version it used.

**Review.**
- Version 1 holds typical retail values, marked DEMO and `unreviewed`.
- Every calculation made with an unreviewed specification says so in its warnings.
- A reviewer records a review with `mark_reviewed`, which stores the reviewer and the time.
- `compare_with_provider` lists any difference from a provider's published values. Differences are never applied automatically.
- The specifications are synced by the daily `forex_maintenance` job and when the feed starts.

## 3. The calculation

**Pip value.**
- The pip value per lot in the quote currency is contract size × pip size.
- In the account currency, it is converted at a stored rate. The rate is 1 only when the quote currency is the account currency.
- There is no fixed pip value anywhere: the tests check USD-quoted, JPY and cross pairs in several account currencies.

**The rate.** `conversion.resolve` takes, in order:
1. the same currency;
2. a direct pair, or its inverse;
3. a cross through USD.

Each leg is the latest stored mid. The rate is kept as an exact fraction (numerator over denominator), so 1 / 150 is never rounded before the size is floored. The response shows the rate, its path, the time of its oldest quote, its data types and whether it is stale. A pair in the less liquid tier always counts as indicative. With no path, the request is refused with 422: a rate is never assumed.

**Costs.**
- **Spread:** taken from the pair's latest quote when that quote is fresh. Otherwise it is unknown, counted as zero, and a warning says the costs are understated.
- **Slippage and commission:** from the specification, counted for entry and exit.
- **Not included:** swaps and financing, as the response states.

**Size.** The size is in units of the base currency:
- It is computed in the quote currency with a single division.
- It is rounded down to the lot step, so the planned loss at the stop, with costs, never exceeds balance × risk percent. A property test checks this exactly, and also checks that one more lot step would exceed it.
- Below the minimum lot size, nothing is sized. Above the maximum, the size is capped with a warning.

**Outputs:**
- size, in units and lots;
- pip value, in the quote and account currencies;
- stop and target in pips;
- risk amount;
- loss before and after costs;
- profit before and after costs;
- risk/reward before and after costs;
- costs: spread, slippage, commission and total;
- notional, margin and margin use;
- position leverage, and the maximum leverage the specification allows;
- account impact;
- signed exposure per currency.

## 4. API

Both endpoints need sign-in and the forex flag; when the flag is off they answer 404.

`POST /api/v1/forex/risk/calculate`
- **Body:** `instrument`, `direction`, `entry`, `stop`, optional `target`, `balance`, `account_currency` and `risk_percent`. All amounts are decimal strings.
- **Response:** the outputs above, plus the conversion, the specification reference, the limits, warnings, disclosures and a notice.
- **422:** an unknown pair, a stop or target on the wrong side, a bad value, or no stored conversion rate.

`GET /api/v1/forex/contract-specs` returns the active specification of each active pair, with its review status.

## 5. Warnings and disclosures

**Warnings** report a breach; they never change the result silently. Each limit is a setting:

| Warning | When |
|---|---|
| Risk limit | The risk percent is above `forex_risk_max_percent` (2) |
| Leverage limit | Position leverage is above `forex_risk_max_leverage` (30) |
| Insufficient margin | The margin exceeds the balance |
| Margin use | The margin uses more than `forex_risk_max_margin_use_percent` (50) of the balance |
| Rate quality | The conversion rate is not a tradable quote (simulated, indicative or delayed), or it is stale |
| Unknown spread | No fresh quote |
| Unreviewed specification | The specification has not been reviewed |
| Less liquid pair | The pair is in the exotic tier |
| Size | The position was not sized (below the minimum) or was capped |

**Disclosures** are in every response:
- A stop-loss does not guarantee the maximum loss: prices can gap or slip past it, for example over a weekend or around news.
- Leverage amplifies losses as well as gains.
- The values are estimates. The calculator is for study and paper trading, not advice.

The guarantee-language guard runs over every warning and disclosure.

## 6. Differences from the plan, and open items

- **Migration 0023.** The wave table in EXECUTION_PLAN says T07 adds no migration. That note predates DEC-24, which chose a reviewed, versioned table, so T07 adds migration 0023 for `forex_contract_specs`.
- **Limits that need positions.** The design lists loss limits per day and per week, and an exposure limit per currency across positions. These need paper positions, so they arrived with paper trading (P13-T09; this document first said P13-T10 in error): see [forex-paper-trading.md](forex-paper-trading.md) section 4. For a single trade, exposure as a share of the balance equals the position leverage, so the leverage limit covers it.
- **Margin closeout.** Closeout levels depend on the broker. Until the specifications are reviewed against a broker, the margin-use warning stands in for them.
- **Specification review.** The specifications must be reviewed before any real use. The forex module stays fixture-only and off outside development (DEC-19, DEC-20, DEC-23).
