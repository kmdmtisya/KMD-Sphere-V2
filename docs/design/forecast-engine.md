# Compound forecast engine: formulas and rounding

Status: Implemented in P06-T01 (`backend/app/modules/forecasting/engine.py`). Pure Python, no I/O, no LLM, no binary floating point. The API (P06-T02) and goals (P06-T06) call it. The mobile app never projects (DEC-03).

A forecast is an illustration of the assumptions the user supplies. It is never a prediction or a guaranteed return, and every response carries that notice.

## Inputs

| Input | Meaning | Unit |
|---|---|---|
| `initial` (PV) | Amount invested at the start (time 0) | money, >= 0 |
| `contribution` (C) | Amount paid in each contribution period of the first year | money, >= 0 |
| `contribution_frequency` (k) | Contributions per year: monthly 12, quarterly 4, yearly 1 | |
| `contribution_growth` (g) | Yearly increase of the contribution (escalation) | percent, >= 0 |
| `annual_return` (r) | Assumed **nominal** annual return, compounded `compounding_frequency` times a year | percent, may be negative |
| `compounding_frequency` (m) | Compounding periods per year: 12, 4 or 1 | |
| `annual_fee` (f) | Yearly fee charged on the balance (expense ratio, platform fee) | percent, >= 0 |
| `inflation` (pi) | Assumed yearly inflation, used only for the real (today's money) values | percent, >= 0 |
| `years` (n) | Horizon in whole years | 1 to 60 |

The input limits the API accepts are published with the API (P06-T02) and mirrored by the mobile calculator.

## Formulas

Percentages are divided by 100 first (r, f, g, pi below are fractions).

1. **Net periodic rate.** The fee accrues on the same balance as the return, so per compounding period the balance grows by `i = (r - f) / m`. The rate is nominal: 8% compounded monthly is 8%/12 a month (effective 8.30% a year).
2. **Monthly step.** The engine steps month by month, so any compounding and contribution frequency can be combined. The monthly growth factor is the one equivalent to the compounding: `q = (1 + i)^(m / 12)`.
   - Monthly compounding: `q = 1 + (r - f) / 12` exactly.
   - Yearly compounding: `q = (1 + r - f)^(1/12)`, so a lump sum is worth exactly `PV x (1 + r - f)^t` after t years.
   - A contribution paid between two compounding dates grows at the same equivalent rate (no simple-interest stub).
   - `1 + i` must be positive. With the published limits (r >= -20%, f <= 5%) the worst case is `1 - 0.25 = 0.75`.
3. **Contributions** are paid at the **end** of each contribution period (an ordinary annuity): at the end of every month (k = 12), of months 3, 6, 9, 12 (k = 4) or of month 12 (k = 1) of each year.
4. **Escalation.** The contribution in year y (y = 1 .. n) is `C x (1 + g)^(y - 1)`: it steps up once a year, at the start of each year after the first.
5. **Balance.** Starting from `B_0 = PV`, for month t = 1 .. 12n: `B_t = B_(t-1) x q + (contribution paid at the end of month t, if any)`.
6. **Totals at the horizon.**
   - Nominal value `FV = B_(12n)`.
   - Total contributed `TC = PV + sum of all contributions paid` (the initial amount counts as contributed capital).
   - Projected growth `G = FV - TC` (negative when returns net of fees are negative).
   - Real value (today's money) `FV / (1 + pi)^n`.
7. **Yearly series** for charts: for each year t = 0 .. n, the nominal balance `B_(12t)`, the real value `B_(12t) / (1 + pi)^t`, the cumulative contributions and the growth so far. Year 0 is the initial amount.
8. **Scenarios** (conservative, base, growth) run the same calculation with a different `annual_return` each and everything else unchanged. The user chooses the three rates; the engine does not suggest any.

### Closed forms used to check the engine

When the compounding and contribution frequencies are equal (k = m) and there is no escalation, with `N = m n` periods and per-period rate `i`:

- lump sum: `PV (1 + i)^N`;
- contributions: `C ((1 + i)^N - 1) / i` (or `C N` when `i = 0`).

With yearly escalation and k = m, each year's contributions are a level annuity grown to the horizon: `sum over y of C (1 + g)^(y-1) x s x (1 + i)^(m (n - y))`, where `s = ((1 + i)^m - 1) / i` is one year's annuity factor. The tests compare the month-by-month engine against these closed forms and against published textbook values.

## Required contribution (solver)

Given a target value T at the horizon (nominal, or in today's money when the target is real), find the first-year contribution C that reaches it with every other input fixed.

The final value is linear in C: `FV(C) = FV(0) + C x A`, where `A = FV(1) - FV(0)` is the value of the contribution stream per unit of first-year contribution. Hence

- `C = (T' - FV(0)) / A`, with `T' = T` for a nominal target and `T' = T x (1 + pi)^n` for a target in today's money;
- `C = 0` when `FV(0) >= T'` (the initial amount alone reaches the target, flagged `reached_without_contributions`);
- A is always positive (n >= 1 and `1 + i > 0`), so the solver never iterates and never fails to converge.

## Precision and rounding (ADR-0006)

- Everything is computed in a 50-digit decimal context; fractional powers use the decimal module (deterministic on every platform). Nothing is rounded inside the calculation, and no rounded value is fed back in.
- Money results (series values, final values, totals, the required contribution) are rounded **half-up to the currency's minor units** at the output boundary.
- Growth is derived **after** rounding, `round(FV) - round(TC)`, so contributions plus growth equal the final value exactly in what the user sees.
- Percentages are echoed as given; they are inputs, not results.
- The required contribution is rounded half-up like any other amount, so paying it reaches the target to within rounding: the shortfall is at most half a minor unit times A (on a 20-year monthly plan at 8% with no fee, A is about 589, so at most about 2.95 in the target currency). The unrounded value is used for any further calculation.

## Not modelled

Taxes (no tax assumptions are applied; the guide allows them only where explicitly modelled), withdrawals, contributions at the start of a period, contribution holidays, variable returns (sequence risk) and probability distributions. Each would be an explicit, separately documented extension.

## Relation to the DEMO fixture

`mobile/wealthsphere_app/assets/demo/forecast.json` was written before this engine with a different convention (an effective annual rate `r - f`, so the compounding frequency had no effect). Its values therefore differ slightly from the engine's (base scenario after 20 years: 311,121.57 in the fixture, 321,473.53 from the engine). It stays a labelled DEMO fixture; the live repository (P09-T03) shows engine results.
