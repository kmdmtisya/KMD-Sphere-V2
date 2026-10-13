# Portfolio Doctor (P12-T01)

Status: implemented in P12-T01.
- **Code:** `backend/app/modules/doctor/`:
  - `rules.py`: the checks; pure, Decimal only;
  - `service.py`: gathers the existing analytics;
  - `schemas.py` and `api.py`.
- **AI tool:** `backend/app/ai/tools/doctor.py`.
- **Methods:** [financial-methods.md](../financial-methods.md) section 16.
- **Product intent:** [SOLUTION_INTENT.md](../SOLUTION_INTENT.md) section 18.

## 1. What it is

A health check of one of the user's portfolios. Each check compares a figure the platform already computes with a stated threshold and reports a **severity**. The Doctor adds no new valuation. The language model does not produce, change or grade findings: it can only explain them, through the `get_portfolio_diagnosis` tool, which returns exactly what the API returns.

Findings describe; they never instruct. Scenarios are hypothetical shares, never orders. Nothing is bought, sold or prepared for trading (CLAUDE.md: no automatic trade execution).

## 2. API

`POST /api/v1/ai/portfolio-doctor` with `{"portfolio_id": "..."}`.
- Another user's portfolio is not found (404, the same answer as an unknown id). Unknown fields are refused (422).
- The answer is cached per user, like the analytics API, and recomputed after any of their writes.

| Field | Meaning |
|---|---|
| `overall` | the highest severity among flagged findings (`ok` when none) |
| `counts` | flagged findings by severity |
| `complete` | false when some holdings have no value or rate |
| `findings` | every check, always in the order of section 3 |
| `scenarios` | hypothetical caps for a flagged holding or asset class; `is_trade` is always false |
| `notice` | "Observations from your own data against stated thresholds. Not investment advice. Scenarios are hypothetical: nothing is bought or sold." |

A finding has:
- `check` and `status`: `ok`, `flagged`, or `not_assessed` (the message says why);
- `severity`: `ok` < `info` < `low` < `medium` < `high`;
- a factual `message`;
- `metric`, `unit` (`percent` or `count`), `value`, and the `threshold` reached;
- `subject`: an asset id, class, sector, country, goal ids or `cash_interest`;
- `assumptions`.

Percentages are published to 2 decimals, half-up (ADR-0006).

## 3. Checks and thresholds

Shares are of the portfolio's total value in its base currency. A measure at or above a threshold takes that level.

| Check | Measure | Low | Medium | High | Not assessed when |
|---|---|---|---|---|---|
| `position_concentration` | largest holding (cash balances are not holdings) | 10% | 20% | 35% | no valued holdings |
| `asset_class_concentration` | largest asset class (cash is a class) | — | 70% | 90% | — |
| `sector_concentration` | largest known sector | — | 30% | 50% | no holding has a sector |
| `geographic_concentration` | largest known country | 75% | 90% | — | no holding has a country |
| `currency_exposure` | value not in the base currency | 25% | 50% | 75% | — |
| `liquidity` | cash and holdings that can usually be sold within days | — | below 25% | below 10% | — |
| `volatility` | annualised volatility of the monthly series (risk.md) | 10% | 20% | 30% | less than 12 monthly returns, or incomplete history |
| `drawdown` | largest fall from a previous peak | 10% | 20% | 35% | as volatility |
| `income_dependence` | largest payer's share of trailing 12-month gross income | — | 50% | 75% | no income in 12 months |
| `goal_alignment` | goals linked to this portfolio: overdue is high, behind is medium | | | | no linked goal |
| `data_completeness` | unpriced holdings: an `info` finding | | | | — |

**Notes:**
- Sector and country use only recorded values. When at least 50% of the holdings' value has no sector (or country), and nothing else is flagged, the check gives an `info` finding saying that it covers only part of the portfolio. Cash never counts as unknown.
- **Liquidity is an assumption about the asset class,** stated in every liquidity finding:

  | Liquidity | Asset classes |
  |---|---|
  | Immediate | cash, money market funds |
  | Market (days) | stocks, ETFs, bonds, mutual funds, REITs, crypto, commodities |
  | Term (until maturity or notice) | fixed deposits, SACCO holdings, pensions |
  | Illiquid | real estate, private business, private equity |
  | Unknown | custom assets |

  A test fails if an asset class has no stated liquidity.
- Volatility and drawdown describe the past of the portfolio's own data, not a forecast. Goal status is an estimate under each goal's assumptions (goals.md). Both say so in `assumptions`.
- A portfolio with no value, or with a negative balance, is not assessed: shares of its total would mean nothing.
- The findings are the same whatever the input order. Equal holdings resolve by id.

These thresholds are the T01 defaults. They are constants in `Thresholds` and can be reviewed with the P12-T08 results.

## 4. Scenarios

When `position_concentration` or `asset_class_concentration` is flagged, a scenario shows the measures if that share were capped:
- the largest holding at 20%;
- the largest class at 60%.

The difference is spread over the rest of the portfolio in proportion to its current shares, so the shares still add up to 100%.

The scenario gives:
- the shares before and after (percent);
- the resulting effective number of positions (for a holding) or the asset-class HHI (for a class).

It gives **no amount to buy or sell**, ignores prices, fees and taxes, and is marked `is_trade: false`. It has no scenario when there is nothing to spread over, such as a single holding.

## 5. The assistant

`get_portfolio_diagnosis(portfolio_id)` is on the allow-list ([ai-governance.md](../ai-governance.md)):
- It is owner-scoped, and a smuggled `user_id` is refused.
- Its description tells the model to explain the findings and not to add, change or grade any.
- Answers still go through the answer policy (P10-T08): numbers must come from tool results, and guarantee language is refused.
- The routing evaluation has eight Doctor questions.
