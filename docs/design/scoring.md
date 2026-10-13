# Instrument features and explainable scores (P12-T03)

Status: implemented in P12-T03.
- **Code:** `backend/app/modules/scoring/`:
  - `features.py`: pure;
  - `scoring.py`: pure;
  - `service.py`, `schemas.py` and `api.py`.
- **Formulas:** [financial-methods.md](../financial-methods.md) section 17. Requirements Q-01 to Q-06 in the financial test matrix.

## 1. What a score is

A number from 0 to 100 that summarises an instrument's **measured characteristics**:
- how much its price moved (stability) and fell (resilience) over the last year;
- its past price change (momentum);
- its cost (expense ratio, funds only);
- its liquidity, assumed from the class;
- the source's risk level.

A score is **not a forecast, not an expected return and not a recommendation**. Every response says so. It ranks universe instruments for the opportunity pipeline (P12-T06). The language model never computes or changes it.

## 2. Explainable by construction

- Each factor's points come from a stated transform (financial-methods section 17).
- The score is the weighted mean of the measured factors. Its **contributions** (effective weight × points) therefore add up to it exactly. The API rounds each part to 2 decimals.
- Every factor has a plain explanation, such as "Volatility of 18.2% a year over the last year: 69.67/100".

## 3. Missing data is never ignored

Each factor has a status:

| Status | Meaning | Effect |
|---|---|---|
| `used` | measured | contributes |
| `missing` | applies but could not be measured: short history, no prices, a fund without an expense ratio, unknown liquidity | listed with its reason; lowers **coverage** (measured / applicable weight) and confidence |
| `not_applicable` | does not apply (an expense ratio for a share) | left out without penalty |

| Confidence | When |
|---|---|
| `high` | coverage of at least 85% and fresh prices |
| `medium` | coverage of at least 60% |
| `low` | coverage below 60% |
| `none` | coverage below 50%: no score at all |

Stale prices, meaning a latest close more than 4 days old, keep confidence below high, and the reasons say why.

Manually valued instruments (bonds, money market funds, deposits, property) have no market prices. So only liquidity and risk class can be measured, which is 30% of the applicable 90%, and they are not scored. This is honest: there is no price history to describe.

## 4. Weights

`OPPORTUNITY_SCORE_WEIGHTS` (settings) sets the weights. They must name every factor, none may be negative, and they must add up to 1; startup fails otherwise.

The defaults are stability 25%, resilience 20%, momentum 15%, cost 10%, liquidity 15% and risk class 15%. The user reviews them with the P12-T08 results (advance approval, 2026-10-13).

## 5. API

`GET /api/v1/universe/scores` (optional `asset_class`, `eligible_only`) returns:
- the weights;
- per instrument: whether it is eligible for the signed-in user (P12-T02), the date of the last close used, and the score block (score, coverage, confidence, factors, reasons).

Instruments are sorted by score, highest first, with unscored ones last. The score itself does not depend on the user.

## 6. Data

- **Closes:** read from `market_prices`, one per day (the most recently retrieved), over the trailing 365 days.
- **Expense ratios:** fund metadata (`expense_ratio`). The DEMO universe gives its ETFs illustrative ratios, and ingestion now stores any metadata the asset class defines.
- **Development:** in development and CI, closes come from the fake provider through the existing backfill. Tests insert their own closes.
