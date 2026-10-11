# Value history and risk metrics

Status: Implemented in P06-T08.

- **Value history:** `backend/app/modules/portfolio/history.py` (pure).
- **Risk maths:** `backend/app/modules/analytics/risk.py` (pure, Decimal only).
- **Service:** `backend/app/modules/portfolio/risk_service.py`. It is published by the analytics API (P06-T09) and reviewed in P06-T10.

Risk figures describe the past of the user's own data. They are not forecasts.

## 1. Value history

The portfolio's value at the **end of each date** of a series, in its base currency, applies the summary's rules (docs/design/portfolio-summary.md) as of that date:

- **Positions:**
  - The ledger (reversed entries and their reversals left out) gives each asset's quantity on the date.
  - An asset with a positive quantity is valued at its newest valuation dated up to the end of the day (UTC).
  - A held asset with no valuation yet is **unpriced**.
  - An asset known only from valuations (never traded, such as a house added by valuation) counts from its first valuation.
  - A position with quantity 0 is not valued.
- **Cash:** each currency's balance on the date, from the same cash rules as the summary.
- **Conversion:** amounts in another currency use the **historical rate** for that date. That is the P05-T06 rule: the newest rate at or before the end of the day, at most 7 days old, with the opposite pair inverted only when there is no direct rate. A currency without such a rate is **unconverted** and left out.
- **Completeness:** a point is `complete` only when nothing is unpriced or unconverted.
- **`flow_next`:** the external flows (docs/design/performance.md, section 1) after the date up to the next date.

### Dates

| Frequency | Dates (periods a year) |
|---|---|
| daily | every day from start to end (365) |
| weekly | start, then every 7 days, and end (52) |
| monthly | start, the last day of each month in between, and end (12) |

- By default the series starts at the first ledger entry or valuation and ends today.
- The end cannot be after today.
- A series has at most 1,000 points; a longer range needs a longer frequency.

Market prices (P08) will value listed assets on each date. Until then, an asset is valued only on dates when the user had entered a valuation for it.

## 2. Period returns

For each period from point k to point k+1:

`r = V(k+1) / (V(k) + F(k)) - 1`

Here V is the end-of-day value and F(k) is the period's external flows, counted at the **start** of the period. This removes deposits and withdrawals from the return (time-weighted).

- A period that starts and ends empty has no return.
- A period that starts at zero or below but ends with a value makes the series **undefined**.
- Counting flows at the start is exact when flows fall on the point dates. Otherwise it is an approximation that daily points make negligible; P06-T10 reviews it.

The series' time-weighted return is the T03 `twr` of the same points (docs/design/performance.md, section 6).

## 3. Volatility

- **Period volatility** = the sample standard deviation (n - 1) of the period returns.
- **Volatility** = period volatility x sqrt(periods a year): 365 for daily, 52 for weekly, 12 for monthly.

Square roots use the decimal module (34 digits, deterministic).

## 4. Maximum drawdown

The largest fall of the **return index**, measured from a running peak. The return index is the growth of 1 linking the period returns, so flows do not count as gains or losses. Results:

- `depth`: the fall from the peak, a fraction <= 0 (for example -0.25 is a 25% fall);
- `peak`: when the peak was set;
- `trough`: the lowest point after it;
- `recovered`: when the index first regained the peak, or null if it has not.

The earliest of equal falls is reported. A series that never falls has depth 0.

## 5. Statuses: no guessing

| Status | When | Figures |
|---|---|---|
| `ok` | a complete series with at least 6 period returns | all |
| `insufficient_data` | fewer than 6 period returns (a new portfolio, a short range) | the returns only |
| `incomplete_data` | any point in the range has unpriced positions or unconverted currencies | none (with the number of incomplete points) |
| `undefined_period` | a period starts at zero or below but ends with a value | none |

Six returns is a deliberately low floor (half a year of months). Volatility from few returns is very uncertain; the API states the number of returns with the figure.

## 6. Precision

All figures are unrounded: 50 digits for values and 34 for returns and roots. The API publishes percentages to 2 decimals, half-up (ADR-0006).
