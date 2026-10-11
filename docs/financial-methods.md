# Financial methods

Status: Reviewed and approved by the user on 2026-10-11 (P06-T10.3), with the decisions in section 14.

This document lists every formula WealthSphere uses to produce a financial figure. For each one it gives the derivation or definition, the rounding, the edge cases, and where it is **checked independently**. The detailed design documents are linked; this is the single place to review them.

**Principles (CLAUDE.md, SOLUTION_INTENT):**
- The backend is the only place figures are computed. The app displays them and never derives them (DEC-03).
- No binary floating point. Money, quantities and rates are Decimal internally (50 digits, 34 for roots and fractional powers) and strings in JSON (ADR-0003).
- Nothing is rounded inside a calculation. Rounding happens once, at the output (section 13).
- Missing data is reported (unpriced, unconverted, insufficient), never guessed.
- Forecasts, goal statuses and scenarios are illustrations of stated assumptions, never guaranteed; past performance is labelled as such.

## How the formulas are checked

| Check | What it is | Where |
|---|---|---|
| Golden vectors | Hand-computed or published values (for example Excel's XIRR example, compound-interest tables) | `backend/tests/golden/*.json`, each module's tests |
| Closed forms | The month-by-month engines are compared with annuity and lump-sum formulas | `tests/forecasting/test_engine.py` |
| **Independent oracle** | A second implementation of every formula, written from this document with exact rational arithmetic (`fractions.Fraction`), sharing no code with the application. Hypothesis generates random ledgers and inputs, and the results must agree to 1e-30 (exactly, for rounded outputs). | `backend/tests/oracle.py`, `backend/tests/test_cross_check.py` |
| Different algorithm | Where the result is irrational (XIRR, CAGR, fractional powers, square roots), a different method at higher precision: Newton's method at 80 digits for XIRR, exact variance for volatility | same |
| Properties | Invariants that must always hold (contributions + growth = value, weights add up to 100, flows do not change TWR, and so on) | each module's tests |
| Mutation checks | Bugs injected into the code must make the tests fail; done for every P05/P06 task (recorded in EXECUTION_LOG.md) | task evidence |

## 1. Money, rounding and allocation (ADR-0003, ADR-0006)

- **Amounts:** Decimal internally, strings in JSON (`{"amount": "1234.50", "currency": "USD"}`). JSON numbers are refused on input.
- **Minor units:** ISO 4217 (JPY 0, KWD and BHD 3, others 2). A posted amount with more decimals is refused, never rounded.
- **Rounding:** **ROUND_HALF_UP** (ties away from zero): 2.345 becomes 2.35 and -2.345 becomes -2.35.
- **Largest-remainder allocation** (percentages that must add up to exactly 100.00):
  1. Each part's exact share × 100 is floored to 0.01.
  2. The missing hundredths go one each to the largest remainders.
  3. Ties go to the earlier part.

  Shares are undefined (null) when the total is not positive or any part is negative.
- **Independent check:** the oracle's `half_up` and `largest_remainder` agree with the application on random inputs. Three equal parts give 33.34 / 33.33 / 33.33.

## 2. Ledger postings (P05-T04)

- **Gross amount** = quantity × unit price for trades. When the gross is given, it must agree to within one minor unit (brokers round).
- **Posting rate:** an amount in another currency is converted at the posting's rate `fx` (1 unit of posting currency = `fx` of the portfolio currency). It is stored with 12 decimals, and is the historical rate for the trade date when not supplied (section 5).
- **Corrections** are reversals. A reversed entry and its reversal are both left out of every calculation, as if never posted.
- **Order:** trade date, then creation time, then id.

## 3. Holdings: weighted average cost (ADR-0012, docs/design/holdings in ADR)

Per asset and portfolio, in the portfolio currency, each posting at its own rate:

| Entry | Quantity | Cost basis | Realised | Income / expenses |
|---|---|---|---|---|
| BUY, TRANSFER_IN | + q | + (gross + fees + taxes) × fx | | |
| SELL | - q | - cost × q / quantity (all of it when selling everything) | + (gross - fees - taxes) × fx - cost removed | |
| TRANSFER_OUT | - q | - cost × q / quantity | none | |
| DIVIDEND, COUPON, RENT, DISTRIBUTION, INTEREST (with asset) | | | | income + gross × fx; expenses + (fees + taxes) × fx |
| FEE, TAX (with asset) | | | | expenses + (gross + fees + taxes) × fx |

**Worked example (also an oracle vector):**

| Step | Quantity | Cost basis | Average | Realised |
|---|---|---|---|---|
| Buy 10 for 1,000 + 4 fee | 10 | 1,004 | | |
| Buy 10 for 1,200 | 20 | 2,204 | 110.20 | |
| Sell 5 for 650 - 2 fee | 15 | 2,204 - 551 = 1,653.00 | 110.20 | 648 - 551 = 97.00 |

- A sale is refused if it would make the quantity negative on any date of the history.
- **Independent check:** the oracle recomputes quantity, cost, realised, income and expenses for random ledgers (buys, partial sells, transfers, dividends, fees, reversals, foreign rates) and agrees exactly.

## 4. Portfolio summary (docs/design/portfolio-summary.md)

- **Cash** per currency = Σ cash effects:
  - DEPOSIT, SELL and income types: + gross - fees - taxes;
  - WITHDRAWAL: -(gross + fees + taxes);
  - BUY, FEE, TAX: -(gross + fees + taxes);
  - TRANSFER_IN, TRANSFER_OUT: -(fees + taxes).
- **Positions** are valued at their latest valuation (market prices arrive in P08), converted at the latest rate. Closed positions are not valued; unpriced ones are listed.
- **Totals:**
  - total value = valued positions + cash;
  - unrealised P&L = value - cost basis (positions with a ledger cost);
  - net contributions = deposits - withdrawals.
- **Consolidated:** each portfolio's figures are converted from its base currency at the latest rate.
- **Freshness:** `data_as_of` is the **oldest** input used; `complete` means nothing is unpriced or unconverted.
- **Independent check:** cash, holdings value, unrealised and realised P&L and net contributions agree with the oracle on random ledgers.

## 5. FX (P05-T06, docs/design/multi-currency-design.md)

- **Historical rate** (postings, value history): the newest stored rate at or before the end of the day (UTC), at most **7 days** old.
- **Latest rate** (current values): the newest stored rate; stale after 1 day (shown, not hidden).
- **Opposite pair:** used (inverted, 1/rate) only when no direct rate exists.
- **Ties:** newest timestamp, then newest retrieval, then provider name.
- **No usable rate:** the amount is left out and reported (`unconverted`), never converted at 1 or at a guess.

## 6. Allocation and concentration (docs/design/allocation.md)

- **Parts:** each valued position and each currency's cash balance.
- **Dimensions:** asset class (cash is `cash`), currency of the valuation, country (asset data) and sector (`sector` metadata). Missing values go to an unclassified slice.
- **Weights:** largest remainder (section 1); null with negative parts.
- **Concentration:**
  - HHI = Σ wᵢ² (fractions; 1/n to 1);
  - effective positions = 1 / HHI;
  - top-1/3/5 shares and the largest position.
- **Independent check:** weights and HHI agree with the oracle.

## 7. Performance (docs/design/performance.md)

- **External flows** (portfolio currency, at posting rates): deposits and transfers in (+); withdrawals and transfers out (-).
- **Profit/loss** = total value - net invested.
- **Assumed deposits:** where a posting would take a currency's cash below zero, the shortfall is treated as a deposit on that date at that posting's rate, for performance and risk only; it is reported separately (`assumed_deposits`). Without any money in (no deposits and no purchases), return figures are still undefined.
- **Simple return** = profit / contributions (inflows, including assumed deposits). Null when nothing was put in.
- **CAGR** = (end / start)^(365/days) - 1, only for at least 365 days.
- **XIRR** solves Σ aᵢ / (1 + r)^((dᵢ - d₀)/365) = 0, with spreadsheet day count (actual/365):
  - same-day flows are netted;
  - a fixed rate grid finds the sign change nearest 10%, then bisection narrows it to 1e-12;
  - outcomes are explicit: `insufficient_flows`, `no_sign_change` or `no_rate_in_range`;
  - `unique` is true when the flows change sign once.
- **TWR** = Π V(k+1) / (V(k) + F(k)) - 1, with flows at the start of each sub-period and empty periods skipped. It is annualised only for at least a year.
- **Independent checks:**
  - XIRR matches Microsoft's published Excel example (0.373362535; our net present value residual is 2e-9 against Excel's -8.6e-6), and agrees with **Newton's method at 80 digits** to 1e-9 on random cash-flow sets.
  - TWR agrees with the exact rational product.
  - Gain and simple return agree with the oracle.

## 8. Income and passive income (docs/design/income.md)

- **Income events:** one per DIVIDEND, INTEREST, COUPON, RENT or DISTRIBUTION entry, kept in step with the ledger and checked against it after every step of the integrity suite.
- **Amounts:** gross, fees, taxes and net = gross - fees - taxes, in the portfolio currency at each payment's posting rate.
- **Trailing twelve months (TTM):** after the same day a year earlier, up to and including today (29 February counts from 28 February).
- **Passive income:** yearly = TTM net; monthly = TTM net / 12.
- **Months and years:** the 12 calendar months ending this month, and calendar years.
- **Yields** (on gross, trailing):
  - current yield = TTM gross / position value;
  - yield on cost = TTM gross / cost basis;
  - portfolio yield = TTM gross / total value.
- **Across portfolios:** each portfolio's TTM is converted at the latest rate; unconverted portfolios are reported.
- **Independent check:** totals agree with the oracle's exact sums.

## 9. Compound forecasts (docs/design/forecast-engine.md)

- **Return:** the return r is **nominal**, compounded m times a year. The fee accrues on the same balance, so the period rate is i = (r - f) / m.
- **Monthly stepping:** q = (1 + i)^(m/12), so any compounding and contribution frequency combine.
- **Contributions:** paid at the **end** of each period, stepping up by g once a year.
- **Totals:**
  - balance B(t) = B(t-1) × q + payment;
  - contributions include the initial amount;
  - growth = value - contributions, after rounding;
  - real value = nominal / (1 + π)^(years).
- **Scenarios:** the same inputs with the user's three returns.
- **Required contribution:** the final value is linear in the contribution C, so C = (T' - FV(0)) / (FV(1) - FV(0)), and the solver never iterates. The result is **rounded up** to the currency's minor units (ADR-0006 exception 1), so paying it always reaches the target.
- **Independent checks:**
  - published tables: 10,000 at 5% yearly for 10 years = 16,288.95, and 100 a month at 6% for 10 years = 16,387.93;
  - closed forms for every frequency mix;
  - the oracle's exact monthly simulation (with escalation and quarterly or yearly contributions);
  - the exact annuity formula for the required contribution.

## 10. Goals (docs/design/goals.md)

- **Inputs:** the current value is the funding portfolios' value in the goal's currency (a negative value counts as 0).
- **Measures:**
  - progress = value / target (0 to 100%);
  - gap = target - value;
  - months left = whole months to the date.
- **Projections:** each scenario from the current value, with month horizons. A target in today's money is compared after dividing by (1 + π)^(months/12).
- **Status:** `on_track` if already reached or the base projection meets the target; otherwise `behind`. This is an estimate; it is labelled as such and never presented as certain.
- **Required contribution:** the base scenario's, by the date (null when reached, overdue, or when no contribution falls before the date). Estimated completion is the first month the base scenario reaches the target.
- **Independent check:** the oracle's annuity closed form for horizons of 1 to 720 months.

## 11. Net worth (docs/design/net-worth.md)

- **Formula:** net worth = total assets (active portfolios, consolidated) - total liabilities (each converted at the latest rate).
- **Rounding:** each liability is rounded first; totals are sums of rounded values, so assets - liabilities = net worth exactly as shown.
- **FX provenance:** every rate used (rate, time, provider, stale, inverted).
- **Unconverted:** left out and reported.
- **Independent check:** the oracle reproduces the rounded totals exactly.

## 12. Value history and risk (docs/design/risk.md)

- **Value history:** the end-of-day value at each date, from the ledger as of that date, the newest valuation, and the historical rate. A point is complete only when nothing is unpriced or unconverted.
- **Period returns:** Modified Dietz, r = (V_end - V_start - F) / (V_start + Σ wᵢFᵢ), with w = (period end - t + 1) / days for a flow made at the start of day t (daily series: w = 1). The series' time-weighted return links the period returns.
- **Volatility:** sample standard deviation (n - 1) × √(periods a year): 365, 52 or 12.
- **Maximum drawdown:** on the linked return index (flows removed), with peak, trough and recovery dates.
- **Statuses:** `insufficient_data` (< 12 returns), `incomplete_data`, `undefined_period`. No partial figures are given.
- **Independent checks:**
  - volatility² equals the exact rational sample variance (× periods a year);
  - alternating ±10% monthly gives exactly 40.00% annualised;
  - cross-checked with Python's `statistics.stdev`.

## 13. Rounding at the output (ADR-0006)

| Figure | Published as |
|---|---|
| Amounts | the currency's minor units, half-up |
| Rates, returns, shares, yields, volatility, drawdown | percent, 2 decimals, half-up (trailing zeros dropped: "8.5") |
| Weights that must add up to 100 | largest remainder, 2 decimals |
| HHI | 4 decimals; effective positions 2 |
| Posting FX rate | 12 decimals (stored) |
| Holdings cache | 8 decimals (stored); quantity 12 |
| Forecast and goal amounts | minor units, half-up; growth = rounded value - rounded contributions. **Exception:** required contributions are rounded up |
| Net worth | rounded lines, totals summed from them |

## 14. Review decisions (P06-T10.3)

The user approved the following on 2026-10-11 (the recommendations were put to the user and approved as proposed). Items marked *changed* altered the implementation; the others confirmed it.

| # | Decision | Outcome |
|---|---|---|
| 1 | Purchases recorded without deposits | **Changed.** The cash shortfall counts as an assumed deposit on its date (section 7, performance.md section 8), reported separately. |
| 2 | Fees in forecasts | Confirmed: subtracted from the rate, (r - f) / m. |
| 3 | Forecast return | Confirmed: nominal, compounded at the chosen frequency. The DEMO fixture will be regenerated in P09-T03. |
| 4 | Flows in risk returns | **Changed.** Modified Dietz, flows weighted by the days invested (section 12); daily series unchanged. |
| 5 | Yields | Confirmed: on gross income, before withholding tax. |
| 6 | Minimum history for risk | **Changed.** 12 period returns (was 6). |
| 7 | Required contribution rounding | **Changed.** Rounded up, so paying it always reaches the target (ADR-0006 exception 1). |
| 8 | CAGR | Confirmed: only for periods of at least a year; shorter periods show the simple return. |

## 15. Cross-check vectors (the "workbook")

Each value below was computed by the independent oracle (exact arithmetic) and is asserted against the application in `tests/test_cross_check.py`, or in the module tests named.

| # | Inputs | Expected |
|---|---|---|
| 1 | Forecast: 10,000 + 500 a month, 8% - 0.5% fee, monthly, 20 years | 321,473.53 nominal; 130,000.00 paid in |
| 2 | Goal: 1,000,000 in 240 months from 10,000 at 8% - 0.5% | 1,725.38 a month (1,725.3726 rounded up) |
| 3 | Holdings: section 3's example | cost 1,653.00; realised 97.00; average 110.20 |
| 4 | Allocation: three equal parts | 33.34 / 33.33 / 33.33 |
| 5 | TWR: 0 + 1,000 → 1,100, + 500 → 1,760 | 21% |
| 6 | Variance of +10%, -10%, +10%, -10% | 1/75 exactly; × 12 = 0.16, so 40.00% annualised |
| 7 | XIRR: Excel's example (-10,000; 2,750; 4,250; 3,250; 2,750) | 0.3733625335 (Excel: 0.373362535 within its 1e-8 tolerance) |
| 8 | Lump sum and annuity tables | 16,288.95; 16,387.93 |
