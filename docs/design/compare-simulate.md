# Compare and Simulate (P12-T07)

Status: implemented in P12-T07.
- **Code:** `backend/app/modules/compare/`.
- **Product intent:** [SOLUTION_INTENT.md](../SOLUTION_INTENT.md) sections 19 and 20.
- **Acceptance:** future returns appear only as assumptions or scenarios.

Both endpoints are deterministic: no model is involved. Both work on instruments of the investment universe ([investment-universe.md](investment-universe.md)), and an unknown instrument is not found.

## 1. Compare: `POST /api/v1/ai/compare`

**Request:** `asset_ids` (2 to 5, no repeats, kept in the order given), and optionally `portfolio_id` with `amount`. These two go together.

**Per instrument, side by side:**

| Field | Meaning |
|---|---|
| asset class, country, currency, risk level, liquidity, minimum investment | recorded facts |
| `expense_ratio_percent` | fees (funds only) |
| `income_yield` | always null for now: no distribution data is stored yet, and the field says so |
| `past` | price change, volatility and largest fall over the last year, the last close, and weeks of prices; labelled past, null without prices |
| `score` | the explainable score ([scoring.md](scoring.md)) |
| `eligible`, `eligibility_reasons` | for the signed-in user |
| `research_horizon` | a stated assumption ([opportunities.md](opportunities.md)) |
| `diversification` | with a portfolio and an amount, the compatibility result ([compatibility.md](compatibility.md)) |

**No future return appears in a comparison.** A test checks that no field name carries an expected, projected or forecast value. The only text about the future is the disclaimer "past, not a forecast".

## 2. Simulate: `POST /api/v1/ai/simulate`

**Request:** `asset_id`, `assumptions` (the scenario forecast inputs, P06-T02) and optionally `portfolio_id`.

- **Returns are the user's:**
  - the user states conservative, base and growth returns, and the forecast engine's own validation applies (conservative ≤ base ≤ growth);
  - **there is no default return**, and none comes from data or a model;
  - `returns_source` is always `your_assumptions`.
- **Same engine:** the result is exactly what `POST /api/v1/forecasts/scenarios` returns for the same inputs (tested).
- **Notes, deterministic:**
  - the instrument's recorded expense ratio, when it differs from the assumed fee;
  - a different pricing currency, because exchange-rate moves are not modelled;
  - always: "Returns are your assumptions, not a forecast of this instrument; real returns vary from year to year and can be negative."
- **Fit:** with a portfolio, the initial investment's compatibility is checked. It must be in the portfolio's base currency.
- **Notice:** "An illustration under the return assumptions you entered, not a forecast of this instrument. Real returns vary and can be negative; nothing is guaranteed."

## 3. Access

- Both endpoints need a signed-in user.
- Another user's portfolio is not found.
- Unknown fields are refused.
- Nothing is bought or changed.
