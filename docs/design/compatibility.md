# Portfolio compatibility and suitability (P12-T04)

Status: implemented in P12-T04.
- **Code:** `backend/app/modules/compatibility/`:
  - `impact.py`: pure;
  - `service.py`, `schemas.py` and `api.py`.
- **Method:** [financial-methods.md](../financial-methods.md) section 18. Requirements U-01 to U-03 in the financial test matrix.

## 1. The question

"What would adding this amount of a universe instrument do to my portfolio, and does it fit?"

**Request:** `POST /api/v1/universe/compatibility` with `portfolio_id`, `asset_id` (a universe instrument) and `amount` (in the portfolio's base currency).

**Answer:**
- the portfolio's measures before and after;
- the Portfolio Doctor checks whose severity would change;
- a verdict with its reasons.

It is a hypothetical calculation for analysis: `is_trade` is always false, nothing is bought, and the portfolio is unchanged (a test checks the holdings afterwards).

## 2. How it is computed

- **New money:** the amount is added as new money, and nothing is sold. The instrument's holding grows by the amount, or a new holding appears.
- **Same rules as today:** the portfolio is re-measured with the same deterministic analytics and the same Doctor rules (`diagnose`) used by `POST /api/v1/ai/portfolio-doctor`.
- **No new judgement:** the before and after come from one code path, so the comparison adds nothing new.

| Measure | Meaning |
|---|---|
| `instrument_share_percent` | the instrument's share of the portfolio |
| `largest_holding_percent` | the largest holding's share |
| `effective_positions` | 1 / HHI of the holdings and cash |
| `asset_class_percent` | the share of the instrument's asset class |
| `foreign_currency_percent` | value not in the base currency |
| `accessible_percent` | cash and assets that can usually be sold within days |

## 3. Verdict

| Verdict | When | Reason codes |
|---|---|---|
| `not_suitable` | an eligibility rule fails for the user (P12-T02), or the amount is below the instrument's minimum investment | `eligibility_<rule>`, `below_minimum` |
| `caution` | the minimum could not be checked (no rate to its currency); a Doctor check gets worse and ends at medium or high; or the instrument would be more than 20% of the portfolio (the Doctor's medium holding threshold) | `minimum_unchecked`, `worsens_<check>`, `large_holding` |
| `fits` | none of the above | — |

The minimum is in the instrument's currency. The amount is converted at the latest stored rate (FX service, cross through the pivot where needed).

A check that only moves to `info`, such as an unknown-country share passing 50%, is reported in `doctor_changes` but is not a reason for caution.

## 4. Access

- The portfolio must be the user's: another user's portfolio is not found, the same answer as an unknown id.
- The instrument must be in the universe (404 otherwise).
- The amount must be positive and in the portfolio's base currency (422 otherwise).
- Unknown fields are refused.
