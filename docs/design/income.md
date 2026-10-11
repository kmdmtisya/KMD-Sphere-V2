# Income and passive income

Status: Implemented in P06-T05.
- **Events:** `income_events` (migration 0007) and `backend/app/modules/transactions/income_events_service.py`.
- **Figures:** pure functions in `backend/app/modules/networth/income.py`, and the per-portfolio service in `backend/app/modules/networth/income_service.py`.

Published by the analytics API (P06-T09), reviewed in P06-T10.

## 1. Income events

Income is what a portfolio receives without selling anything:

| Type | Linked to an asset |
|---|---|
| DIVIDEND | yes |
| COUPON | yes |
| RENT | yes |
| DISTRIBUTION | yes |
| INTEREST | optional (cash interest has no asset) |

Each ledger entry of these types has exactly one row in `income_events`, linked by `transaction_id` (unique, foreign key). The row records:
- the portfolio and the asset;
- the type and the date paid (the entry's trade date);
- the currency;
- the gross amount, fees and taxes (for example withholding);
- the posting's rate to the portfolio currency.

**Kept in step with the ledger:**
- The row is written in the same database transaction as the ledger entry.
- When an entry is reversed, its row is deleted in the reversal's transaction. A reversal itself never has a row.
- An idempotent replay posts nothing, so it adds no row.
- The table can always be rebuilt from the ledger. The integrity suite checks after every step of its random sequences that it equals the ledger's effective income entries.
- Migration 0007 copied in the income entries that existed before the table.

The ledger stays the source of truth; the table is an index for income queries.

## 2. Amounts

Every amount is converted to the portfolio's base currency at its posting's own rate, the rate on the day it was received (ADR-0012). Later rate moves do not change income already received.

- gross = the amount received before deductions;
- fees and taxes as recorded (withholding tax is a tax);
- net = gross - fees - taxes.

## 3. Periods

| Figure | Definition |
|---|---|
| Trailing twelve months (TTM) | payments after the same day one year earlier, up to and including today. From 29 February, the year before is counted from 28 February. |
| `yearly` (passive income a year) | TTM net |
| `monthly_average` (passive income a month) | TTM net / 12 |
| Months | the 12 calendar months ending with the current month, oldest first, including months without income (so the current month is month to date) |
| Years | every calendar year with income, oldest first |

The TTM window and the 12 calendar months differ slightly: a payment in the same month a year ago, after today's day of the month, is in the TTM but not in the months.

## 4. By asset and by type

For each asset that has paid income (with cash interest as "no asset"), the result gives TTM and all-time totals. It also gives:
- `current_yield` = TTM gross / the position's current value (from the summary). It is `null` when the position is not valued or is closed.
- `yield_on_cost` = TTM gross / the position's cost basis (ADR-0012). It is `null` when there is no open cost.

Assets are ordered by TTM gross, then all-time gross, largest first. Types are listed alphabetically, each with TTM and all-time totals.

## 5. Portfolio yield

`portfolio_yield` = TTM gross / the portfolio's total value (summary). It is `null` when the total value is not positive. Gross is used, the usual convention for yields. The result carries the summary's `complete` flag, because unpriced assets understate the value and so overstate the yield.

Yields are trailing: they describe income already received, not a forecast. Income from positions since sold still counts in the TTM.

## 6. Precision

The figures are unrounded, computed at 50 digits. The API publishes amounts to the currency's minor units and yields as percentages to 2 decimals, half-up (ADR-0006).
