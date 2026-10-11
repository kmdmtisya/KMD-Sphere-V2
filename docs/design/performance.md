# Performance: profit, returns, CAGR, XIRR and time-weighted return

Status: Implemented in P06-T03. The maths is pure and deterministic: `backend/app/modules/analytics/performance.py` uses Decimal only, with no I/O and no LLM. `backend/app/modules/portfolio/performance_service.py` applies it to one portfolio from its ledger and summary. It is published by the analytics API (P06-T09) and reviewed in P06-T10.

The modules follow the dependency table in docs/architecture.md: analytics depends on transactions and market data, and portfolio depends on analytics.

## 1. External flows

Performance separates what the investor puts in or takes out (external flows) from what the investments earn. The amounts below are in the portfolio's base currency, each at its posting's own FX rate. Reversed entries and their reversals are left out.

| Type | External flow (into the portfolio) |
|---|---|
| DEPOSIT | + gross |
| WITHDRAWAL | - gross |
| TRANSFER_IN | + gross (the value of the units brought in) |
| TRANSFER_OUT | - gross (the value of the units taken out) |
| everything else | none: trades, income, fees and taxes happen inside the portfolio |

Fees and taxes charged on a deposit or withdrawal are costs inside the portfolio, so they lower the return. A forward split posted as a zero-value TRANSFER_IN (ADR-0012) is not a flow.

- `contributions` = the sum of inflows (deposits and transfers in).
- `withdrawals` = the sum of outflows (withdrawals and transfers out).
- `net_invested` = contributions - withdrawals.

The summary's `net_contributions` counts deposits and withdrawals only. Performance also counts transfers, because a portfolio funded by transferring shares in would otherwise show their whole value as profit.

## 2. Profit

- `total_gain` = `total_value` - `net_invested`. This is everything the portfolio has earned: price changes, income, minus fees and taxes. `total_value` is the summary's (positions valued from valuations, plus cash).
- The breakdown comes from the summary: `realized_pl`, `unrealized_pl`, `income` and `expenses` (docs/design/portfolio-summary.md).
- When the summary is incomplete (unpriced assets or currencies without a rate), the figures leave those amounts out. The result says so (`complete: false`) and is never presented as complete.

## 3. Simple return

`simple_return` = `total_gain` / `contributions`: the gain relative to everything put in. It is not annualised and ignores timing; use the money-weighted return to account for timing. It is undefined (`null`) when nothing was put in.

`net_invested` is not the denominator, because after large withdrawals it can be zero or negative.

## 4. CAGR

`CAGR = (end_value / start_value)^(365 / days) - 1` between two values with no flows in between (actual/365 day count).

- Defined only when `start_value > 0`, `end_value >= 0` and the period is at least 365 days. Annualising a shorter period would extrapolate it.
- An end value of 0 gives -100%.

## 5. Money-weighted return (XIRR)

The annual rate r at which the investor's dated flows have zero net present value, with the same day count as spreadsheet XIRR (actual/365):

`sum over i of a_i / (1 + r)^((d_i - d_0) / 365) = 0`

**Investor flows:**
- each contribution as a negative amount on its date;
- each withdrawal as a positive amount on its date;
- the current `total_value` as a positive amount on the valuation date (today, or the requested date).

**Algorithm (deterministic, always terminates):**
1. Flows on the same date are added together, and zero amounts are dropped.
2. The net present value is evaluated on a fixed grid of rates from -99.99% to +1,000,000% a year.
3. The bracket (adjacent grid points where the value changes sign) closest to 10%, the usual spreadsheet starting guess, is chosen.
4. That bracket is narrowed by bisection until it is narrower than 1e-12 (at most 200 steps). Arithmetic uses 34 significant digits.

**Outcomes (`status`):**

| Status | When | Rate |
|---|---|---|
| `ok` | a root was found | the annual rate (-0.9999 to 10,000) |
| `insufficient_flows` | fewer than two non-zero flows on different dates (for example a single flow, or only zeros) | null |
| `no_sign_change` | every flow has the same sign: there is nothing to earn a return on | null |
| `no_rate_in_range` | the net present value never changes sign between -99.99% and +1,000,000% | null |

- `unique` is true when the flows change sign exactly once in date order. In that case the rate is the only one.
- With more sign changes several rates can solve the equation; the one closest to 10% is reported and `unique` is false.
- For periods shorter than a year the rate is still annualised. The analytics API (P06-T09) shows the simple return in that case.

## 6. Time-weighted return (TWR)

TWR removes the effect of the timing and size of external flows, so it measures the investments rather than the investor.

**Inputs:** a date-ordered series of points. Each point has:
- the portfolio's value just before any external flow that day;
- the external flow that day (positive into the portfolio, negative out).

**Formula:** sub-period k runs from point k (after its flow) to point k+1 (before its flow):

`TWR = product over k of V_(k+1) / (V_k + F_k) - 1`

The flow on the last point is after the end of the measurement and is ignored. The annualised TWR, `(1 + TWR)^(365 / days) - 1`, is given only for periods of at least 365 days.

**Outcomes (`status`):**

| Status | When |
|---|---|
| `ok` | computed |
| `insufficient_data` | fewer than two points |
| `undefined_period` | a sub-period starts at zero or below (V_k + F_k <= 0) but ends with a value; or a value is negative |

- A sub-period that starts and ends at zero (an emptied portfolio waiting for the next deposit) has no return. It is skipped (factor 1).
- Dates must be strictly increasing.
- The portfolio's historical value series arrives with P06-T08. Until then, TWR is available as a tested function, and the portfolio service reports the money-weighted and simple returns.

## 7. Precision and rounding

- Calculations use the decimal module (34 digits for XIRR and TWR powers, 50 elsewhere). Nothing is rounded inside a calculation.
- Rates are returned unrounded. The API (P06-T09) publishes percentages to 2 decimals and amounts to the currency's minor units, half-up (ADR-0006).

## 8. Assumed deposits (P06-T10 review, decision 1)

Many people record purchases without the deposits that paid for them. Without a deposit there are no external flows, and a return cannot be defined. So, **for performance and risk**, wherever a posting would take a currency's cash below zero, the shortfall is treated as a deposit:

- made on that posting's date (just before it), in that currency, at that posting's FX rate;
- never stored and never shown as a transaction;
- included in `contributions`, `net_invested`, the money-weighted flows and the value series, so the return is defined;
- reported separately as `assumed_deposits` (in the base currency) and `assumed_deposit_count`, so the figures are never presented as based only on recorded deposits.

Each currency has its own cash, a sale or income adds to it before a later purchase, and a withdrawal beyond the balance is covered the same way. Reversed entries are ignored.

**The summary does not assume anything.** It still shows negative cash as it is (docs/design/portfolio-summary.md, section 3), so the performance `total_value` can be higher than the summary's by the assumed deposits.
